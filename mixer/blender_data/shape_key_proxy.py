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
from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context
    from mixer.blender_data.struct_proxy import StructProxy


DEBUG = True

logger = logging.getLogger(__name__)


class ShapeKeyHandler:
    def __init__(self, proxy: DatablockProxy):
        self._pending_creation = ""
        """Uuid of the shape key proxy whose creation is pending"""

    @property
    def pending_creation(self):
        return self._pending_creation

    @pending_creation.setter
    def pending_creation(self, shape_key_uuid: str):
        self._pending_creation = shape_key_uuid

    def _create_shape_keys(self, object_datablock: T.Object, key_blocks_proxy: StructCollectionProxy) -> T.Key:
        for _ in range(len(key_blocks_proxy)):
            object_datablock.shape_key_add()

        return object_datablock.data.shape_keys

    def create_shape_keys_datablock(self, object_datablock: T.Object, context: Context):
        if not self._pending_creation:
            return

        shape_key_proxy = context.proxy_state.proxies[self._pending_creation]
        assert isinstance(shape_key_proxy, ShapeKeyProxy)

        key_blocks_proxy: StructCollectionProxy = shape_key_proxy.data("key_blocks")
        shape_key_datablock = self._create_shape_keys(object_datablock, key_blocks_proxy)
        shape_key_proxy.save(shape_key_datablock, bpy.data.shape_keys, shape_key_datablock, context)

        shape_key_uuid = shape_key_proxy.mixer_uuid
        assert shape_key_uuid in context.proxy_state.datablocks

        shape_key_datablock.mixer_uuid = shape_key_uuid
        context.proxy_state.datablocks[shape_key_uuid] = shape_key_datablock

        self._pending_creation = ""

    def update_shape_key_datablock(self, object_datablock: T.Object, context: Context):
        if not self._pending_creation:
            return

        object_datablock.shape_key_clear()
        self.create_shape_keys_datablock(object_datablock, context)


class ShapeKeyProxy(DatablockProxy):
    """
    Proxy for a ShapeKey datablock.

    Exists because the Key.key_blocks API (shape_key_add, shape_key_remove, ...) is in fact in Object
    """

    # TODO move bpy_data_ctor_shape_keys into create_standalone_datablock here

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

            # Delegate the Blender update to the first Object.apply() call, which will call
            # ShapeKeyHandler.update_shape_key_datablock()
            data_uuid = attribute.user.mixer_uuid
            data_proxy = context.proxy_state.proxies[data_uuid]
            assert hasattr(data_proxy, "shape_key_handler")

            shape_key_handler = data_proxy.shape_key_handler
            shape_key_handler.pending_creation = attribute.mixer_uuid

            # Update the proxy only
            return super().apply(attribute, parent, key, delta, context, False)
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

            # The DG does not trigger an Object update, so tell the ObjectProxy to fake an Object update
            # so that the Object API can be called
            context.visit_state.dirty_shape_keys.add(datablock.mixer_uuid)

            # Ensure that the whole Key data is available to be reloaded after clear()
            self.load(datablock, context)
            return DeltaReplace(self)
        else:
            # this delta is processed by the regular apply
            return super().diff(datablock, key, prop, context)
