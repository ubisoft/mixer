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
from typing import TYPE_CHECKING

import bpy.types as T  # noqa

from mixer.blender_data.datablock_proxy import DatablockProxy

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context


DEBUG = True

logger = logging.getLogger(__name__)


class ObjectProxy(DatablockProxy):
    """
    Proxy for a Object datablock. This specialization is required to handle properties with that are accessible
    with an API instead of data read /write, such as vertex groups
    """

    def _save(self, datablock: T.Object, context: Context) -> T.Object:
        super()._save(datablock, context)

        #
        # Vertex groups are read in MeshProxy and written here
        #
        vertex_groups_proxy = self._data["vertex_groups"]
        if vertex_groups_proxy is None or vertex_groups_proxy.length == 0:
            return datablock

        datablock_ref_proxy = self._data["data"]
        data_datablock = datablock_ref_proxy.target(context)
        if data_datablock is None:
            # Empty
            return datablock

        data_proxy = context.proxy_state.proxies.get(datablock_ref_proxy.mixer_uuid)
        data_proxy_meta = getattr(data_proxy, "_meta", None)
        if data_proxy_meta is None:
            logger.error("Object has vertex groups, but data proxy has none")
            return datablock

        data_vertex_groups = data_proxy_meta.get("vertex_groups")
        if data_vertex_groups is None:
            logger.error("Object has vertex groups, but data proxy has none")
            return datablock

        vertex_groups = datablock.vertex_groups
        vertex_groups.clear()
        groups_data = [
            (item._data["index"], item._data["lock_weight"], item._data["name"])
            for item in vertex_groups_proxy._sequence
        ]
        groups_data.sort(key=lambda x: x[0])

        for index, lock_weight, name in groups_data:
            vertex_group = vertex_groups.new(name=name)
            vertex_group.lock_weight = lock_weight
            data_vertex_group = data_vertex_groups.get(str(index), None)
            if data_vertex_group is None:
                logger.error(f"vertex group {index} found in {datablock} but not in data")
                continue

            for index, weight in data_vertex_group:
                vertex_group.add([index], weight, "ADD")

        return datablock
