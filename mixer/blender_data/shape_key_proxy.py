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
Proxy for Key datablock

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context
    from mixer.blender_data.datablock_proxy import DatablockProxy


DEBUG = True

logger = logging.getLogger(__name__)


class ShapeKeyHandler:
    def __init__(self, proxy: DatablockProxy):
        self._proxy = proxy
        self._pending_creation = ""
        """Uuid of the shape key proxy whose creation is pending"""

    @property
    def pending_creation(self):
        return self._pending_creation

    @pending_creation.setter
    def pending_creation(self, value: str):
        self._pending_creation = value

    def create_shape_keys_datablock(self, object_datablock: T.Object, context: Context):
        if not self._pending_creation:
            return

        shape_key_proxy = context.proxy_state.proxies[self._pending_creation]
        key_blocks_proxy: StructCollectionProxy = shape_key_proxy.data("key_blocks")
        for _ in range(len(key_blocks_proxy)):
            object_datablock.shape_key_add()

        shape_key_datablock = object_datablock.data.shape_keys
        shape_key_proxy.save(shape_key_datablock, bpy.data.shape_keys, shape_key_datablock, context)

        shape_key_uuid = shape_key_proxy.mixer_uuid
        assert shape_key_uuid in context.proxy_state.datablocks
        assert context.proxy_state.datablocks[shape_key_uuid] is None

        shape_key_datablock.mixer_uuid = shape_key_uuid
        context.proxy_state.datablocks[shape_key_uuid] = shape_key_datablock

        self._pending_creation = ""
