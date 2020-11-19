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
Proxy for Mesh datablock

See synchronization.md
"""
from __future__ import annotations

from collections import defaultdict
import logging
from typing import Dict, List, Optional, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.proxy import DeltaReplace, DeltaUpdate


if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context


DEBUG = True

logger = logging.getLogger(__name__)


_mesh_geometry_properties = {
    "edges",
    "loop_triangles",
    "loops",
    "polygons",
    "vertices",
}
"""If the size of any of these has changes clear_geomtry() is required. Is is not necessary to check for
other properties (uv_layers), as they are redundant checks"""

mesh_resend_on_clear = {
    "edges",
    "face_maps",
    "loops",
    "loop_triangles",
    "polygons",
    "vertices",
    "uv_layers",
    "vertex_colors",
}
"""if geometry needs to be cleared, these arrays must be resend, as they will need to be reloaded by the receiver"""


def update_requires_clear_geometry(incoming_update: MeshProxy, existing_proxy: MeshProxy) -> bool:
    """Determine if applying incoming_update requires to clear the geometry of existing_proxy"""
    geometry_updates = _mesh_geometry_properties & set(incoming_update._data.keys())
    for k in geometry_updates:
        existing_length = existing_proxy._data[k].length
        incoming_soa = incoming_update.data(k)
        if incoming_soa:
            incoming_length = incoming_soa.length
            if existing_length != incoming_length:
                logger.debug("apply: length mismatch %s.%s ", existing_proxy, k)
                return True
    return False


def _compute_vertex_groups(datablock: T.Mesh):
    indices: Dict[int, List[int]] = defaultdict(list)
    weights: Dict[int, List[float]] = defaultdict(list)
    for i, vertex in enumerate(datablock.vertices):
        for element in vertex.groups:
            group = element.group
            indices[group].append(i)
            weights[group].append(element.weight)

    groups = indices.keys()
    # used in ObjectProxy._save()

    # with arrays: cannot serialize as-is
    # self._meta["vertex_groups"] = {
    #     group: (array("I", indices[group]), array("f", weights[group])) for group in groups
    # }

    return {str(group): [indices[group], weights[group]] for group in groups}


class MeshProxy(DatablockProxy):
    """
    Proxy for a Mesh datablock. This specialization is required to handle geometry resize processing, that
    spans across Mesh (for clear_geometry()) and geometry arrays of structures (Mesh.vertices.add() and others)
    """

    # TODO find another name than meta
    # TODO send as buffers
    # TODO weighs representation (sort by weights to speed up load, compress weights is applicable)
    _serialize = ("_meta",)

    def __init__(self):
        super().__init__()
        self._meta = {}

    def requires_clear_geometry(self, mesh: T.Mesh) -> bool:
        """Determines if the difference between mesh and self will require a clear_geometry() on the receiver side"""
        for k in _mesh_geometry_properties:
            soa = getattr(mesh, k)
            existing_length = len(soa)
            incoming_soa = self.data(k)
            if incoming_soa:
                incoming_length = incoming_soa.length
                if existing_length != incoming_length:
                    logger.debug(
                        "need_clear_geometry: %s.%s (current/incoming) (%s/%s)",
                        mesh,
                        k,
                        existing_length,
                        incoming_length,
                    )
                    return True
        return False

    def load(
        self,
        datablock: T.ID,
        key: str,
        context: Context,
        bpy_data_collection_name: str = None,
    ) -> MeshProxy:
        super().load(datablock, key, context, bpy_data_collection_name)
        self._meta["vertex_groups"] = _compute_vertex_groups(datablock)
        return self

    def _diff(
        self, struct: T.Mesh, key: str, prop: T.Property, context: Context, diff: MeshProxy
    ) -> Optional[Union[DeltaUpdate, DeltaReplace]]:

        if self.requires_clear_geometry(struct):
            # If any mesh buffer changes requires a clear geometry on the receiver, the receiver will clear all
            # buffers, including uv_layers and vertex_colors.
            # Resend everything
            diff.load(struct, key, context)

            # force ObjectProxy._diff to resend the Vertex groups
            logger.debug(f"_diff: {struct} requires clear_geometry: replace")
            context.visit_state.dirty_vertex_groups.add(struct.mixer_uuid)
            return DeltaReplace(diff)
        else:
            if prop is not None:
                context.visit_state.path.append(key)
            try:
                vertex_groups = _compute_vertex_groups(struct)
                if vertex_groups != self._meta["vertex_groups"]:
                    logger.debug(f"_diff: {struct} dirty vertex groups")
                    # force Object update. This requires that Object updates are processed later, which seems to be
                    # the order  they are listed in Depsgraph.updates
                    context.visit_state.dirty_vertex_groups.add(struct.mixer_uuid)
                    diff._meta["vertex_groups"] = vertex_groups

                properties = context.synchronized_properties.properties(struct)
                properties = specifics.conditional_properties(struct, properties)
                for k, member_property in properties:
                    try:
                        member = getattr(struct, k)
                    except AttributeError:
                        logger.warning(f"diff: unknown attribute {k} in {struct}")
                        continue

                    proxy_data = self._data.get(k)
                    delta = diff_attribute(member, k, member_property, proxy_data, context)

                    if delta is not None:
                        diff._data[k] = delta

            finally:
                if prop is not None:
                    context.visit_state.path.pop()

            if len(diff._data) or len(diff._meta):
                return DeltaUpdate(diff)

            return None

    def apply(
        self,
        parent: T.BlendDataMeshes,
        key: str,
        struct_delta: DeltaUpdate,
        context: Context,
        to_blender: bool = True,
    ) -> MeshProxy:

        struct = parent.get(key)
        struct_update = struct_delta.value

        try:
            self._meta["vertex_groups"] = struct_update._meta["vertex_groups"]
        except KeyError:
            pass

        if isinstance(struct_delta, DeltaReplace):
            self.copy_data(struct_update)
            if to_blender:
                struct.clear_geometry()
                self.save(parent, key, context)
        else:
            # collection resizing will be done in AosProxy.apply()

            context.visit_state.path.append(key)
            try:
                for k, member_delta in struct_update._data.items():
                    current_value = self._data.get(k)
                    try:
                        self._data[k] = apply_attribute(struct, k, current_value, member_delta, context, to_blender)
                    except Exception as e:
                        logger.warning(f"Struct.apply(). Processing {member_delta}")
                        logger.warning(f"... for {struct}.{k}")
                        logger.warning(f"... Exception: {e!r}")
                        logger.warning("... Update ignored")
                        continue
            finally:
                context.visit_state.path.pop()

            # If a face is removed from a cube, the vertices array is unchanged but the polygon array is changed.
            # We expect to receive soa updates for arrays that have been modified, but not for unmodified arrays.
            # however unmodified arrays must be reloaded if clear_geometry was called

        return self
