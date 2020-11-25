# GPLv3 License
#
# Copyright (C) 2020 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
Proxy for Object datablock

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.mesh_proxy import VertexGroups
from mixer.blender_data.misc_proxies import NonePtrProxy
from mixer.blender_data.proxy import DeltaReplace, DeltaUpdate
from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context, Proxy
    from mixer.blender_data.struct_proxy import StructProxy


DEBUG = True

logger = logging.getLogger(__name__)

_vertex_group_prop = T.Object.bl_rna.properties["vertex_groups"].fixed_type


def _window_area():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                return window, area
    return None, None


class ObjectProxy(DatablockProxy):
    """
    Proxy for a Object datablock. This specialization is required to handle properties with that are accessible
    with an API instead of data read /write, such as vertex groups
    """

    def _save(self, datablock: T.Object, context: Context) -> T.Object:
        # TODO remove extra work done here. The vertex groups array is created in super()._save(), then cleared in
        # update_vertex_groups(), because diff() requires clear().
        self._fit_material_slots(datablock, self._data["material_slots"], context)
        super()._save(datablock, context)
        self.update_vertex_groups(datablock, self._data["vertex_groups"], context)
        return datablock

    def _fit_material_slots(
        self, object_datablock: T.Object, material_slots_proxy: StructCollectionProxy, context: Context
    ):
        """Adjust the size of object_datablock.material_slots to match the size of material_slots_proxy"""

        # When adding materials to a Mesh and creating an Object for this Mesh, Object.material_slots
        # is populated from the Mesh entries. Aftyerwards, it is necessary to use material slot operators
        if material_slots_proxy is None:
            # from save(): should not happen, from apply(), means unchanged
            return

        material_slots = object_datablock.material_slots

        remove_count = len(material_slots) - len(material_slots_proxy)
        if remove_count == 0:
            return

        # Must use operators, unfortunately
        window, area = _window_area()
        if window is None or area is None:
            raise RuntimeError(f"Cannot update material_slots window: {window} area {area}")

        if remove_count > 0:
            remove_ctx = {"window": window, "object": object_datablock, "scene": bpy.data.scenes[0]}
            for _ in range(remove_count):
                r = bpy.ops.object.material_slot_remove(remove_ctx)
                if "FINISHED" not in r:
                    raise RuntimeError(
                        f"update_material_slots on {object_datablock}: material_slot_remove returned {r}"
                    )
        elif remove_count < 0:
            add_count = -remove_count
            add_ctx = {"object": object_datablock}
            for _ in range(add_count):
                r = bpy.ops.object.material_slot_add(add_ctx)
                if "FINISHED" not in r:
                    raise RuntimeError(f"update_material_slots on {object_datablock}: material_slot_add returned {r}")

    def update_vertex_groups(
        self, object_datablock: T.Object, vertex_groups_proxy: StructCollectionProxy, context: Context
    ):
        """Update vertex groups of object_datablock with information from vertex_groups_proxy (from MeshProxy)"""

        # Vertex groups are read in MeshProxy and written here
        # Correct operation relies on vertex_groups_proxy being a full update (see _diff_must_replace_vertex_groups())
        if vertex_groups_proxy is None or vertex_groups_proxy.length == 0:
            return

        try:
            datablock_ref_proxy = self._data["data"]
        except KeyError:
            # an empty
            return

        try:
            mesh_proxy = context.proxy_state.proxies.get(datablock_ref_proxy.mixer_uuid)
        except KeyError:
            logger.error(
                f"_save(): internal error: {object_datablock} has vertex groups, but its data datablock has None"
            )
            return

        try:
            mesh_vertex_groups_array = mesh_proxy._arrays["vertex_groups"]
        except KeyError:
            return

        vertex_groups = object_datablock.vertex_groups

        # check if the vertex groups can be edited. Checking this Object for OBJECT mode is not enough
        # as another Object using the same Mesh might not be in OBJECT mode
        dummy = vertex_groups.new(name="dummy")
        try:
            dummy.add([0], 1, "ADD")
        except RuntimeError as e:
            # TODO a smarter test. This displays a false error when the update is limited to Object.vertex_groups,
            # the Mesh vertex group data being unchanged.
            logger.error(f"Cannot update vertex groups while in edit mode for {object_datablock}...")
            logger.error(f"... update raises {e!r}")
            logger.error("... vertex group contents not updated")
            return
        finally:
            vertex_groups.remove(dummy)

        mesh_vertex_groups = VertexGroups.from_array_sequence(mesh_vertex_groups_array)

        vertex_groups.clear()
        groups_data = []
        for i in range(vertex_groups_proxy.length):
            item = vertex_groups_proxy.data(i)
            groups_data.append((item.data("index"), item.data("lock_weight"), item.data("name")))

        for index, lock_weight, name in groups_data:
            vertex_group = vertex_groups.new(name=name)
            vertex_group.lock_weight = lock_weight
            try:
                indices, weights = mesh_vertex_groups.group(index)
            except KeyError:
                # empty vertex group
                continue

            for index, weight in zip(indices, weights):
                vertex_group.add([index], weight, "ADD")

    def _diff(
        self, struct: T.Object, key: str, prop: T.Property, context: Context, diff: Proxy
    ) -> Optional[DeltaUpdate]:

        datablock_ref = self._data["data"]
        if datablock_ref and not isinstance(datablock_ref, NonePtrProxy):
            if datablock_ref.mixer_uuid in context.visit_state.dirty_vertex_groups:
                logger.debug(f"_diff: {struct} dirty vertex group: replace")
                # Lazy and heavy : replace the whole Object. Otherwise we would have to merge a DeltaReplace
                # for vertex_groups and a DeltaUpdate for the remaining items
                diff.load(struct, key, context)
                return DeltaReplace(diff)

        return super()._diff(struct, key, prop, context, diff)

    def apply(
        self,
        parent: T.BlendDataObjects,
        key: str,
        struct_delta: DeltaUpdate,
        context: Context,
        to_blender: bool = True,
    ) -> StructProxy:

        update = struct_delta.value
        object_datablock = parent[key]

        if to_blender:
            incoming_material_slots = update.data("material_slots")
            self._fit_material_slots(object_datablock, incoming_material_slots, context)

        updated_proxy = super().apply(parent, key, struct_delta, context, to_blender)

        if to_blender:
            incoming_vertex_groups = update.data("vertex_groups")
            updated_proxy.update_vertex_groups(object_datablock, incoming_vertex_groups, context)
        return updated_proxy
