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
Proxy for Armature datablock

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.json_codec import serialize
from mixer.blender_data.mesh_proxy import VertexGroups
from mixer.blender_data.proxy import Delta, DeltaReplace
from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context, Proxy
    from mixer.blender_data.struct_proxy import StructProxy


DEBUG = True

logger = logging.getLogger(__name__)


class ModeGuard:
    def __init__(self, obj):
        self.obj = obj
        self.previous_mode = bpy.ops.object.mode

    def __enter__(self):
        self.previous_object = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = self.obj
        bpy.ops.object.mode_set(mode = 'EDIT')

    def __exit__(self, type, value, traceback):
        bpy.ops.object.mode_set(mode = self.previous_mode)
        if previous_object:
            bpy.context.view_layer.objects.active = previous_object


@serialize
class ArmatureProxy(DatablockProxy):
    """
    Proxy for an Armature datablock. This specialization is required to switch between current mode and edit mode
    """
    def find_armature_parent_object(self, datablock: T.Armature) -> T.Object:
        for obj in bpy.data.objects:
            if obj.data and obj.data == datablock:
                return obj

    def _save(self, datablock: T.Armature, context: Context) -> T.Armature:                
        obj = self.find_armature_parent_object(datablock)
        if not obj:
            return datablock
        with ModeGuard(obj):
            super()._save(datablock, context)
        return datablock

    def load(self, datablock: T.Armature, context: Context) -> ArmatureProxy:
        obj = self.find_armature_parent_object(datablock)
        if not obj:
            return self
        with ModeGuard(obj):
            super().load(datablock, context)
        return self    


