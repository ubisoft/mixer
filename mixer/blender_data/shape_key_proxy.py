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


class ShapeKeyHandler:
    """Implements Key datablock operations that require the use of the Object shape_key API.

    Each instance of "keyable" datablocks (Mesh, Curve, ...) owns ShapeKeyHandler instance
    """

    def __init__(self, proxy: DatablockProxy):
        self._keyable_proxy: DatablockProxy = proxy
        """Proxy of the Object.data datablock (e.g. Mesh) that owns this ShapeKeyHandler"""

    def create_shape_key_datablock(self, shape_key_proxy: ShapeKeyProxy, context: Context) -> T.Key:
        # find any Object using the shapekeyable
        datablocks = context.proxy_state.datablocks
        data_uuid = self._keyable_proxy.mixer_uuid
        objects = context.proxy_state.objects[data_uuid]
        if not objects:
            logger.error(
                f"update_shape_key_datablock: received an update for {datablocks[shape_key_proxy.mixer_uuid]}..."
            )
            logger.error(
                f"... user {datablocks[self._keyable_proxy.mixer_uuid]} not linked to an object. Update skipped"
            )
            return None
        object_uuid = next(iter(objects))
        object_datablock = datablocks[object_uuid]

        # update the Key datablock using the Object API
        key_blocks_proxy = shape_key_proxy.data("key_blocks")

        object_datablock.shape_key_clear()
        for _ in range(len(key_blocks_proxy)):
            object_datablock.shape_key_add()

        shape_key_datablock = object_datablock.data.shape_keys
        shape_key_proxy.save(shape_key_datablock, bpy.data.shape_keys, shape_key_datablock, context)

        shape_key_uuid = shape_key_proxy.mixer_uuid
        shape_key_datablock.mixer_uuid = shape_key_uuid
        context.proxy_state.datablocks[shape_key_uuid] = shape_key_datablock
        return shape_key_datablock


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

            # Update the proxy only
            result = super().apply(attribute, parent, key, delta, context, False)
            data_proxy.shape_key_handler.create_shape_key_datablock(self, context)

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
