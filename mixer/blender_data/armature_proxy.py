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
from mixer.blender_data.attributes import write_attribute

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context, Proxy
    from mixer.blender_data.struct_proxy import StructProxy


DEBUG = True

logger = logging.getLogger(__name__)


def override_context():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                override = bpy.context.copy()
                override["window"] = window
                override["screen"] = window.screen
                override["area"] = window.screen.areas[0]
                return override
    return None


class ModeGuard:
    def __init__(self, obj):
        self.obj = obj

    def __enter__(self):
        self.ctx = override_context()
        self.previous_mode = self.ctx["mode"]
        self.previous_object = self.ctx["active_object"]
        self.ctx["active_object"] = self.obj
        # self.ctx["view_layer"].objects.active = self.obj
        bpy.ops.object.mode_set(mode="EDIT")

    def __exit__(self, type, value, traceback):
        bpy.ops.object.mode_set(mode=self.previous_mode)
        if self.previous_object:
            self.ctx["active_object"] = self.previous_object


@serialize
class ArmatureProxy(DatablockProxy):
    """
    Proxy for an Armature datablock. This specialization is required to switch between current mode and edit mode
    """

    _edit_bones_map = {}

    def find_armature_parent_object(self, datablock: T.Armature) -> T.Object:
        for obj in bpy.data.objects:
            if obj.data == datablock:
                return obj

    def _save(self, datablock: T.Armature, context: Context) -> T.Armature:
        datablock = self._pre_save(datablock, context)
        if datablock is None:
            logger.warning(f"DatablockProxy.update_standalone_datablock() {self} pre_save returns None")
            return None, None

        with context.visit_state.enter_datablock(self, datablock):
            for k, v in self._data.items():
                if k != "edit_bones":
                    write_attribute(datablock, k, v, context)
                else:
                    ArmatureProxy._edit_bones_map[datablock.mixer_uuid] = v

        self._custom_properties.save(datablock)
        return datablock

    def load(self, datablock: T.Armature, context: Context) -> ArmatureProxy:
        obj = self.find_armature_parent_object(datablock)
        if not obj:
            return self
        with ModeGuard(obj):
            super().load(datablock, context)
        return self

    @staticmethod
    def apply_edit_bones(obj: T.Object, context: Context):
        if not isinstance(obj.data, T.Armature):
            return
        edit_bones = ArmatureProxy._edit_bones_map.get(obj.data.mixer_uuid)
        if not edit_bones:
            logging.error("No edit bones found")
            return

        # hack: resolve collection -> object link
        context.proxy_state.unresolved_refs.resolve(obj.mixer_uuid, obj)

        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")

        write_attribute(obj.data, "edit_bones", edit_bones, context)
        del ArmatureProxy._edit_bones_map[obj.data.mixer_uuid]

        bpy.ops.object.mode_set(mode="OBJECT")
