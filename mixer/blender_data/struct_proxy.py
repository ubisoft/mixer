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
Proxy of a bpy.types.Struct, excluding bpy.types.ID that is implemented in datablock_proxy.py

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.proxy import DeltaReplace, DeltaUpdate, Proxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class StructProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    def __init__(self):
        self._data = {}
        pass

    def copy_data(self, other: StructProxy):
        self._data = other._data

    def clear_data(self):
        self._data.clear()

    def load(self, bl_instance: Any, parent_key: Union[int, str], context: Context):

        """
        Load a Blender object into this proxy
        """
        self.clear_data()
        properties = context.synchronized_properties.properties(bl_instance)
        # includes properties from the bl_rna only, not the "view like" properties like MeshPolygon.edge_keys
        # that we do not want to load anyway
        properties = specifics.conditional_properties(bl_instance, properties)
        context.visit_state.path.append(parent_key)
        try:
            for name, bl_rna_property in properties:
                attr = getattr(bl_instance, name)
                attr_value = read_attribute(attr, name, bl_rna_property, context)
                self._data[name] = attr_value
        finally:
            context.visit_state.path.pop()

        return self

    def _pre_save(self, target: T.bpy_struct, context: Context) -> T.bpy_struct:
        return specifics.pre_save_struct(self, target, context)

    def save(
        self,
        struct: T.bpy_struct,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        context: Context,
    ):
        """
        Save this proxy into attribute

        Args:
            struct: the bpy_struct to store this proxy into
            parent: (e.g an Object instance)
            key: (e.g. "display)
            context: the proxy and visit state
        """
        struct = self._pre_save(struct, context)

        if struct is None:
            if isinstance(parent, T.bpy_prop_collection):
                logger.warning(f"Cannot write to '{parent}', attribute '{key}' because it does not exist.")
            else:
                # Don't log this because it produces too many log messages when participants have plugins
                # f"Note: May be due to a plugin used by the sender and not on this Blender"
                # f"Note: May be due to unimplemented 'use_{key}' implementation for type {type(bl_instance)}"
                # f"Note: May be {bl_instance}.{key} should not have been saved"
                pass

            return

        context.visit_state.path.append(key)
        try:
            for k, v in self._data.items():
                write_attribute(struct, k, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        struct_delta: DeltaUpdate,
        context: Context,
        to_blender: bool = True,
    ) -> StructProxy:
        """
        Apply diff to the Blender attribute at parent[key] or parent.key and update accordingly this proxy entry
        at key.

        Args:
            parent ([type]): [description]
            key ([type]): [description]
            delta ([type]): [description]
            context ([type]): [description]

        Returns:
            [type]: [description]
        """
        if struct_delta is None:
            return

        assert isinstance(key, (int, str))

        struct_update = struct_delta.value
        # TODO duplicate code in StructCollectionProxy.apply()
        if isinstance(key, int):
            struct = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            struct = parent.get(key)
        else:
            struct = getattr(parent, key, None)

        if isinstance(struct_delta, DeltaReplace):
            self.copy_data(struct_update)
            if to_blender:
                self.save(struct, parent, key, context)
        else:

            if to_blender:
                struct = struct_update._pre_save(struct, context)

            assert type(struct_update) == type(self)

            context.visit_state.path.append(key)
            try:
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

        return self

    def diff(self, struct: T.Struct, key: str, prop: T.Property, context: Context) -> Optional[DeltaUpdate]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        As this proxy tracks a Struct or ID, the result will be a DeltaUpdate that contains a StructProxy
        or a DatablockProxy with an Delta item per added, deleted or updated property. One expect only DeltaUpdate,
        although DeltalAddition or DeltaDeletion may be produced when an addon is loaded or unloaded while
        a room is joined. This situation, is not really supported as there is no handler to track
        addon changes.

        Args:
            struct: the Struct that must be diffed against this proxy
            struct_property: the Property of struct as found in its enclosing object
        """

        # Create a proxy that will be populated with attributes differences, resulting in a hollow dict,
        # as opposed as the dense self
        diff = self.__class__()
        diff.init(struct)
        return self._diff(struct, key, prop, context, diff)

    def _diff(
        self, struct: T.Struct, key: str, prop: T.Property, context: Context, diff: StructProxy
    ) -> Optional[DeltaUpdate]:
        # PERF accessing the properties from the synchronized_properties is **far** cheaper that iterating over
        # _data and the getting the properties with
        #   member_property = struct.bl_rna.properties[k]
        # line to which py-spy attributes 20% of the total diff !
        if prop is not None:
            context.visit_state.path.append(key)
        try:
            properties = context.synchronized_properties.properties(struct)
            properties = specifics.conditional_properties(struct, properties)
            for k, member_property in properties:
                # TODO in test_differential.StructDatablockRef.test_remove
                # target et a scene, k is world and v (current world value) is None
                # so diff fails. v should be a BpyIDRefNoneProxy

                # make a difference between None value and no member
                try:
                    member = getattr(struct, k)
                except AttributeError:
                    logger.info(f"diff: unknown attribute {k} in {struct}")
                    continue

                proxy_data = self._data.get(k)
                delta = diff_attribute(member, k, member_property, proxy_data, context)

                if delta is not None:
                    diff._data[k] = delta
        finally:
            if prop is not None:
                context.visit_state.path.pop()

        # TODO detect media updates (reload(), and attach a media descriptor to diff)
        # difficult ?

        # if anything has changed, wrap the hollow proxy in a DeltaUpdate. This may be superfluous but
        # it is homogenous with additions and deletions
        if len(diff._data):
            return DeltaUpdate(diff)

        return None
