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

from mixer.blender_data.attributes import apply_attribute, diff_attribute
from mixer.blender_data.proxy import DeltaUpdate
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data import specifics
from mixer.blender_data.specifics import (
    mesh_resend_on_clear,
    proxy_requires_clear_geometry,
    update_requires_clear_geometry,
)

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context


DEBUG = True

logger = logging.getLogger(__name__)


class MeshProxy(DatablockProxy):
    """
    Proxy for a Mesh datablock. This specialization is required to handle geometry resize processing, that
    spans across Mesh (for clear_geometry()) and geometry arrays of structures (Mesh.vertices.add() and others)
    """

    def _diff(
        self, struct: T.Struct, key: str, prop: T.Property, context: Context, diff: MeshProxy
    ) -> Optional[DeltaUpdate]:
        try:

            # If any mesh buffer change requires a clear geometry on the receiver, send all buffers
            # This is the case if a face is separated from a cube. The number of vertices is unchanged
            # but the number of faces changes, which requires the receiver to call Mesh.clear_geometry(),
            # hence to reload tall the geometry, including parts that were unchanged.
            # As an optimized alternative, it should be possible not to send the unchanged arrays
            # but have MeshProxy.apply() to reload unchanged buffers from in-memory copies.
            force_send_all = proxy_requires_clear_geometry(self, struct)
            if force_send_all:
                logger.debug("requires_clear for %s", struct)

            if prop is not None:
                context.visit_state.path.append(key)

            properties = context.synchronized_properties.properties(struct)
            properties = specifics.conditional_properties(struct, properties)
            for k, member_property in properties:
                try:
                    member = getattr(struct, k)
                except AttributeError:
                    logger.warning(f"diff: unknown attribute {k} in {struct}")
                    continue

                proxy_data = self._data.get(k)
                force_diff = force_send_all and k in mesh_resend_on_clear
                try:
                    if force_diff:
                        context.visit_state.scratchpad["force_soa_diff"] = True
                    delta = diff_attribute(member, k, member_property, proxy_data, context)

                    if delta is not None:
                        diff._data[k] = delta
                    elif force_send_all and k in mesh_resend_on_clear:
                        diff._data[k] = DeltaUpdate.deep_wrap(proxy_data)
                finally:
                    if force_diff:
                        del context.visit_state.scratchpad["force_soa_diff"]

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
        """"""

        struct = parent.get(key)
        struct_update = struct_delta.value

        if to_blender:
            if update_requires_clear_geometry(struct_update, self):
                logger.debug(f"clear_geometry for {struct}")
                struct.clear_geometry()

        # collection resizing will be done in AosProxy.apply()

        try:
            context.visit_state.path.append(key)
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
