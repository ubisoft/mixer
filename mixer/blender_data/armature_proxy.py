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


TODO
- [] bbone_custom_handle_end
- [] handler recursion attempt on edit mode change during armature diff. Is it save to remove the view later from the context ?
- [X] child transformation seems applied twice (once at the parent level, once at the child level)
- [X] bone group
- [] custom_shape_transform

See synchronization.md
"""
from __future__ import annotations

import functools
import logging
from typing import Optional, Union, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.bpy_data_proxy import DeltaUpdate
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.json_codec import serialize

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context
    from mixer.blender_data.proxy import Delta
    from mixer.blender_data.struct_proxy import StructProxy


DEBUG = True

logger = logging.getLogger(__name__)


def override_context():
    # TODO what to do if there is no VIEW_3D
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                override = bpy.context.copy()
                override.update(
                    {
                        "window": window,
                        "screen": window.screen,
                        "area": area,
                    }
                )
                return override

    logger.warning("Not 3D_VIEW for armature update")
    return None


def _restore_active_object(obj: T.Object):
    bpy.context.view_layer.objects.active = obj


def _find_armature_parent_object(datablock: T.Armature) -> Optional[T.Object]:
    # TODO what if the same Armature is linked to several Object datablocks
    objects = [object for object in bpy.data.objects if object.data == datablock]
    if len(objects) > 1:
        logger.warning(f"multiple parents for {datablock!r}")
    try:
        return objects[0]
    except IndexError:
        return None


@serialize
class ArmatureProxy(DatablockProxy):
    """Proxy for an Armature datablock.

    This specialization is required to switch between current mode and edit mode in order to read/write edit_bones.
    """

    _edit_bones_property = T.Armature.bl_rna.properties["edit_bones"]

    def load(self, armature_data: T.Armature, context: Context) -> ArmatureProxy:
        proxy = super().load(armature_data, context)
        assert proxy is self

        armature_object = _find_armature_parent_object(armature_data)
        if not armature_object:
            # Armature without Object (orphan Armature)
            # TODO ensure that the Armature data is synced after being referenced by an Object
            logger.error(f"load: no Object for {armature_data!r} at {context.visit_state.display_path()} ...")
            logger.error(".. Armature data not synchronized")
            return self

        def _read_attribute():
            self._data["edit_bones"] = read_attribute(
                armature_data.edit_bones, "edit_bones", self._edit_bones_property, armature_data, context
            )

        self._access_edit_bones(armature_object, _read_attribute, context)
        return self

    def _save(self, armature_data: T.ID, context: Context) -> T.ID:
        # This is called when the Armature datablock is created. However, edit_bones can only be edited after the
        # armature Object is created and in EDIT mode.
        # So skip edit_bones now and ObjectProxy will call update_edit_bones() later
        edit_bones_proxy = self._data.pop("edit_bones")
        datablock = super()._save(armature_data, context)
        self._data["edit_bones"] = edit_bones_proxy
        return datablock

    def _diff(
        self, armature_data: T.Armature, key: str, prop: T.Property, context: Context, diff: StructProxy
    ) -> Optional[Delta]:

        delta = super()._diff(armature_data, key, prop, context, diff)

        armature_object = _find_armature_parent_object(armature_data)
        if not armature_object:
            # Armature without Object (orphan Armature)
            # TODO ensure that the Armature data is synced after being referenced by an Object
            logger.error(f"load: no Object for {armature_data!r} at {context.visit_state.display_path()} ...")
            logger.error(".. Armature data not synchronized")
            return delta

        def _diff_attribute():
            return diff_attribute(
                armature_data.edit_bones, "edit_bones", self._edit_bones_property, self.data("edit_bones"), context
            )

        edit_bones_delta = self._access_edit_bones(armature_object, _diff_attribute, context)

        if edit_bones_delta is not None:
            if delta is None:
                # create an empty DeltaUpdate
                diff = self.make(armature_data)
                delta = DeltaUpdate(diff)

            # attach the edit_bones delta to the armature delta
            delta.value._data["edit_bones"] = edit_bones_delta

        return delta

    def apply(
        self,
        armature_data: T.Armature,
        parent: T.BlendDataObjects,
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> StructProxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the Object datablock to update
            parent: the attribute that contains attribute (e.g. a bpy.data.objects)
            key: the key that identifies attribute in parent.
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """
        assert isinstance(key, str)

        update = delta.value
        edit_bones_proxy = update._data.pop("edit_bones", None)
        updated_proxy = super().apply(armature_data, parent, key, delta, context, to_blender)
        assert updated_proxy is self
        if edit_bones_proxy is None:
            return self

        update._data["edit_bones"] = edit_bones_proxy

        armature_object = _find_armature_parent_object(armature_data)
        if not armature_object:
            # Armature without Object (orphan Armature)
            # TODO ensure that the Armature data is synced after being referenced by an Object
            logger.error(f"load: no Object for {armature_data!r} at {context.visit_state.display_path()} ...")
            logger.error(".. Armature data not synchronized")
            return self

        def _apply_attribute():
            self._data["edit_bones"] = apply_attribute(
                armature_data, "edit_bones", self._data["edit_bones"], update._data["edit_bones"], context, to_blender
            )

        self._access_edit_bones(armature_object, _apply_attribute, context)

        return self

    @staticmethod
    def update_edit_bones(armature_object: T.Object, context: Context):
        # The Armature datablock is required to create an armature Object, so it has already been received and
        # created. When the Armature datablock was created, its edit_bones member could not be updated since it
        # requires an Object in EDIT mode to be accessible.
        # this implements the update
        assert isinstance(armature_object.data, T.Armature)

        # do we need this at all
        armature_data_uuid = armature_object.data.mixer_uuid
        armature_data_proxy = context.proxy_state.proxies[armature_data_uuid]
        assert isinstance(armature_data_proxy, ArmatureProxy)
        edit_bones_proxy = armature_data_proxy.data("edit_bones")

        def _write_attribute():
            write_attribute(armature_object.data, "edit_bones", edit_bones_proxy, context)

        armature_data_proxy._access_edit_bones(armature_object, _write_attribute, context)

    def _access_edit_bones(self, object: T.Object, func, context: Context):
        # TODO why don't wee need a context override here ?

        cleanup = []

        # 1/ only one object can be in non edit mode : reset active object mode to OBJECT
        previous_mode = bpy.context.mode
        if previous_mode != "OBJECT":
            logger.info(f"_access_edit_bones: DO   set mode to OBJECT for {bpy.context.active_object!r}")
            bpy.ops.object.mode_set(mode="OBJECT")
            cleanup.append(
                (
                    lambda: bpy.ops.object.mode_set(mode=previous_mode),
                    f"_access_edit_bones: UNDO reset mode to {previous_mode} for {bpy.context.active_object!r}",
                )
            )

        try:
            if object not in bpy.context.view_layer.objects.values():
                # the Armature object is not linked to the view layer. Possible reasons:
                # - it is not linked in the source blender data
                # - the code path that created the Armature on the source has not yet linked it to a collection
                # - it is only linked to collections excluded from the view_layer
                # Temporarily link to the current view layer

                # 2/ (optional) link armature Object to scene collection
                objects = bpy.context.view_layer.layer_collection.collection.objects
                logger.info(f"_access_edit_bones: DO   temp link {object!r} to view_layer collection")
                objects.link(object)
                assert object in bpy.context.view_layer.objects.values()
                cleanup.append(
                    (
                        lambda: objects.unlink(object),
                        f"_access_edit_bones: UNDO unlink {object!r} from view_layer collection",
                    )
                )

            # 3/ set armature Object as active
            previous_active_object = bpy.context.view_layer.objects.active
            logger.info(f"_access_edit_bones: DO   change active_object from {previous_active_object!r} to {object!r}")
            bpy.context.view_layer.objects.active = object
            cleanup.append(
                (
                    functools.partial(_restore_active_object, previous_active_object),
                    f"_access_edit_bones: UNDO change active_object from {object!r} to {previous_active_object!r}",
                )
            )

            # 4/ set armature Object to EDIT mode
            logger.info(f"_access_edit_bones: DO   set mode to 'EDIT' for {bpy.context.active_object!r}")
            bpy.ops.object.mode_set(mode="EDIT")
            cleanup.append(
                (
                    lambda: bpy.ops.object.mode_set(mode="OBJECT"),
                    f"_access_edit_bones: UNDO reset mode to 'OBJECT' for {bpy.context.active_object!r}",
                )
            )

            result = func()

        except Exception as e:
            logger.warning(f"update_edit_bones: at {context.visit_state.display_path()}...")
            logger.warning(f"... {e!r}")
        else:
            return result

        finally:
            for f, text in reversed(cleanup):
                try:
                    logger.info(text)
                    f()
                except Exception as e:
                    logger.warning("update_edit_bones: cleanup exception ...")
                    logger.warning(f"... {e!r}")
