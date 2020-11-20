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


class ObjectProxy(DatablockProxy):
    """
    Proxy for a Object datablock. This specialization is required to handle properties with that are accessible
    with an API instead of data read /write, such as vertex groups
    """

    def _save(self, datablock: T.Object, context: Context) -> T.Object:
        super()._save(datablock, context)
        self.update_vertex_groups(datablock, self._data["vertex_groups"], context)
        return datablock

    def update_vertex_groups(
        self, object_datablock: T.Object, vertex_groups_proxy: StructCollectionProxy, context: Context
    ):
        """Update vertex groups of object_datablock with information from vertex_groups_proxy"""

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

        if object_datablock.mode == "EDIT":
            logger.warning(f"Cannot update vertex groups while in edit mode for {object_datablock}...")
            logger.warning(f"... vertex group contents not updated")
            return

        mesh_vertex_groups = VertexGroups.from_array_sequence(mesh_vertex_groups_array)

        vertex_groups = object_datablock.vertex_groups
        vertex_groups.clear()
        groups_data = []
        for i in range(vertex_groups_proxy.length):
            # use data() to resolve updates
            item = vertex_groups_proxy.data(i)
            groups_data.append((item.data("index"), item.data("lock_weight"), item.data("name")))

        # groups_data.sort(key=lambda x: x[0])

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
        updated_proxy = super().apply(parent, key, struct_delta, context, to_blender)
        if to_blender:
            update = struct_delta.value
            incoming_vertex_groups = update.data("vertex_groups")
            logger.debug(f"apply: incoming vg: {incoming_vertex_groups}")
            object_datablock = parent[key]
            updated_proxy.update_vertex_groups(object_datablock, incoming_vertex_groups, context)
        return updated_proxy
