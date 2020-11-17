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

import logging
from typing import Optional, TYPE_CHECKING

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


class MeshProxy(DatablockProxy):
    """
    Proxy for a Mesh datablock. This specialization is required to handle geometry resize processing, that
    spans across Mesh (for clear_geometry()) and geometry arrays of structures (Mesh.vertices.add() and others)
    """

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

    def _diff(
        self, struct: T.Struct, key: str, prop: T.Property, context: Context, diff: MeshProxy
    ) -> Optional[DeltaUpdate]:

        if self.requires_clear_geometry(struct):
            # If any mesh buffer changes requires a clear geometry on the receiver, the receiver will clear all
            # buffers, including uv_layers and vertex_colors.
            # Resend everything

            diff.load(struct, key, context)
            return DeltaReplace(diff)

        if prop is not None:
            context.visit_state.path.append(key)
        try:
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

        if len(diff._data):
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
        if isinstance(struct_delta, DeltaReplace):
            self.copy_data(struct_update)
            if to_blender:
                struct.clear_geometry()
                self.save(parent, key, context)
        else:
            # a sparse update (buffer contents requiring no clear_geometry)
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

        return self
