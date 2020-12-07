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
from typing import Optional, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.proxy import Delta, DeltaReplace

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context
    from mixer.blender_data.struct_proxy import StructProxy


DEBUG = True

logger = logging.getLogger(__name__)


class ShapeKeyProxy(DatablockProxy):
    """
    Proxy for a ShapeKey datablock.

    Exists because the Key.key_blocks API (shape_key_add, shape_key_remove, ...) is in fact in Object
    """

    def create_shape_key_datablock(self, data_proxy: DatablockProxy, context: Context) -> T.Key:
        # find any Object using the datablock manages by this Proxy
        datablocks = context.proxy_state.datablocks
        data_uuid = data_proxy.mixer_uuid
        objects = context.proxy_state.objects[data_uuid]
        if not objects:
            logger.error(f"update_shape_key_datablock: received an update for {datablocks[self.mixer_uuid]}...")
            logger.error(f"... user {datablocks[data_uuid]} not linked to an object. Update skipped")
            return None
        object_uuid = next(iter(objects))
        object_datablock = datablocks[object_uuid]

        # update the Key datablock using the Object API
        key_blocks_proxy = self.data("key_blocks")
        object_datablock.shape_key_clear()  # removes the Key datablock
        for _ in range(len(key_blocks_proxy)):
            object_datablock.shape_key_add()

        new_shape_key_datablock = object_datablock.data.shape_keys
        self.save(new_shape_key_datablock, bpy.data.shape_keys, new_shape_key_datablock.name, context)

        shape_key_uuid = self.mixer_uuid
        new_shape_key_datablock.mixer_uuid = shape_key_uuid
        context.proxy_state.datablocks[shape_key_uuid] = new_shape_key_datablock

        return new_shape_key_datablock

    def load(
        self,
        datablock: T.ID,
        context: Context,
        bpy_data_collection_name: str = None,
    ) -> DatablockProxy:
        super().load(datablock, context, bpy_data_collection_name)

        # ShapeKey.relative_key is a reference into Key.key_blocks. The default synchronization would
        # load save its whole contents for each reference.
        # So relative_key is skipped in the default synchronization, and the Blender reference is translated
        # into a reference by name in Key.key_blocks.
        # diff_must_replace() forces full replacement if any relative_key changes
        key_blocks = datablock.key_blocks
        for key_block_proxy in self._data["key_blocks"]:
            key_block_name = key_block_proxy._data["name"]
            key_block_proxy._data["relative_key"] = key_blocks.get(key_block_name).relative_key.name

        return self

    def save(self, datablock: T.ID, unused_parent: T.bpy_struct, unused_key: str, context: Context) -> T.ID:
        super().save(datablock, unused_parent, unused_key, context)

        # see load()
        key_blocks = datablock.key_blocks
        for key_block_proxy in self._data["key_blocks"]:
            key_block_name = key_block_proxy._data["name"]
            relative_key_name = key_block_proxy._data["relative_key"]
            key_blocks[key_block_name].relative_key = key_blocks[relative_key_name]

        return datablock

    def apply(
        self,
        attribute: T.bpy_struct,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> StructProxy:
        if to_blender and isinstance(delta, DeltaReplace):
            # On the receiver : a full replace is required because Key.key_block must be rebuilt.

            # Update the proxy only
            result = super().apply(attribute, parent, key, delta, context, False)

            # Replace Key
            data_uuid = attribute.user.mixer_uuid
            data_proxy = context.proxy_state.proxies[data_uuid]
            self.create_shape_key_datablock(data_proxy, context)

            return result
        else:
            return super().apply(attribute, parent, key, delta, context, to_blender)

    def diff(self, datablock: T.ID, key: str, prop: T.Property, context: Context) -> Optional[Delta]:
        key_blocks = datablock.key_blocks
        key_bocks_property = datablock.bl_rna.properties["key_blocks"]
        key_blocks_proxy = self._data["key_blocks"]
        must_replace = specifics.diff_must_replace(key_blocks, key_blocks_proxy._sequence, key_bocks_property)
        if must_replace:
            # The Key.key_blocks collection must be replaced, and the receiver must call Object.shape_key_clear(),
            # causing the removal of the Key datablock.

            # Ensure that the whole Key data is available to be reloaded after clear()
            self.load(datablock, context)
            return DeltaReplace(self)
        else:
            # this delta is processed by the regular apply
            return super().diff(datablock, key, prop, context)
