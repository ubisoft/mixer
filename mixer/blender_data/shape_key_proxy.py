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
from typing import Optional, Tuple, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context
    from mixer.blender_data.changeset import RenameChangeset


DEBUG = True

logger = logging.getLogger(__name__)


class ShapeKeyUser:
    def __init__(self):
        self._pending_creation: Optional[ShapeKeyProxy] = None

    def add_pending_shape_key_creation(self, shape_key_proxy: ShapeKeyProxy):
        self._pending_creation = shape_key_proxy

    def create_shape_keys_datablock(self, object_datablock: T.Object, context: Context):
        if self._pending_creation is None:
            return

        key_blocks_proxy: StructCollectionProxy = self._pending_creation.data("key_blocks")
        for _ in range(len(key_blocks_proxy)):
            object_datablock.shape_key_add()

        shape_key_datablock = object_datablock.data.shape_keys
        self._pending_creation.save(shape_key_datablock, bpy.data.shape_keys, shape_key_datablock, context)

        uuid = self._pending_creation.mixer_uuid
        assert uuid in context.proxy_state.datablocks
        assert context.proxy_state.datablocks[uuid] is None

        shape_key_datablock.mixer_uuid = uuid
        context.proxy_state.datablocks[uuid] = shape_key_datablock

        self._pending_creation = None


class ShapeKeyProxy(DatablockProxy):
    """
    Proxy for a ShapeKey datablock.

    XXXX

    """

    def create_standalone_datablock(self, context: Context) -> Tuple[Optional[T.ID], Optional[RenameChangeset]]:
        """
        Save this proxy into its target standalone datablock
        """
        user = self._data["user"]
        user_proxy = context.proxy_state.proxies.get(user.mixer_uuid)
        if user_proxy is None:
            # unresolved ref ?
            # WHAT ?
            pass

        user_proxy.add_pending_shape_key_creation(self)

        return super().create_standalone_datablock(context)
