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
from typing import Optional, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.json_codec import serialize
from mixer.blender_data.proxy import Delta, DeltaReplace, DeltaUpdate, Proxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


@serialize
class StructProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    _serialize = ("_data",)

    def __init__(self):
        self._data = {}
        pass

    def copy_data(self, other: StructProxy):
        self._data = other._data

    def clear_data(self):
        self._data.clear()

    def load(self, attribute: T.bpy_struct, key: Union[int, str], context: Context) -> StructProxy:
        """
        Load the attribute Blender struct into this proxy

        Args:
            attribute: the Blender struct to load into this proxy, (e.g an ObjectDisplay instance)
            key: the identifier of attribute in its parent (e.g. "display")
            context: the proxy and visit state
        """
        self.clear_data()
        properties = context.synchronized_properties.properties(attribute)
        # includes properties from the bl_rna only, not the "view like" properties like MeshPolygon.edge_keys
        # that we do not want to load anyway
        properties = specifics.conditional_properties(attribute, properties)
        context.visit_state.path.append(key)
        try:
            for name, bl_rna_property in properties:
                attr = getattr(attribute, name)
                attr_value = read_attribute(attr, name, bl_rna_property, attribute, context)
                self._data[name] = attr_value
        finally:
            context.visit_state.path.pop()

        return self

    def save(
        self,
        attribute: T.bpy_struct,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        context: Context,
    ):
        """
        Save this proxy into attribute

        Args:
            attribute: the bpy_struct to store this proxy into
            parent: (e.g an Object instance)
            key: (e.g. "display)
            context: the proxy and visit state
        """
        if attribute is None:
            if isinstance(parent, T.bpy_prop_collection):
                logger.warning(f"Cannot write to '{parent}', attribute '{key}' because it does not exist.")
            else:
                # Don't log this because it produces too many log messages when participants have plugins
                # f"Note: May be due to a plugin used by the sender and not on this Blender"
                # f"Note: May be due to unimplemented 'use_{key}' implementation for type {type(bl_instance)}"
                # f"Note: May be {bl_instance}.{key} should not have been saved"
                pass

            return

        specifics.pre_save_struct(self, attribute)
        context.visit_state.path.append(key)
        try:
            for k, v in self._data.items():
                write_attribute(attribute, k, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self,
        attribute: T.bpy_struct,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> StructProxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the struct to update (e.g. a Material instance)
            parent: the attribute that contains attribute (e.g. bpy.data.materials)
            key: the key that identifies attribute in parent (e.g "Material")
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """

        # WARNING parent must not be searched for key as it will fail in case of duplicate keys, with libraries
        update = delta.value

        if isinstance(delta, DeltaReplace):
            self.copy_data(update)
            if to_blender:
                self.save(attribute, parent, key, context)
        else:

            assert type(update) == type(self)

            context.visit_state.path.append(key)
            try:
                for k, member_delta in update._data.items():
                    current_value = self._data.get(k)
                    try:
                        self._data[k] = apply_attribute(attribute, k, current_value, member_delta, context, to_blender)
                    except Exception as e:
                        logger.warning(f"Struct.apply(). Processing {member_delta}")
                        logger.warning(f"... for {attribute}.{k}")
                        logger.warning(f"... Exception: {e!r}")
                        logger.warning("... Update ignored")
                        continue
            finally:
                context.visit_state.path.pop()

        return self

    def diff(
        self, attribute: T.bpy_struct, key: Union[int, str], prop: T.Property, context: Context
    ) -> Optional[Delta]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        As this proxy tracks a Struct or ID, the result will be a DeltaUpdate that contains a StructProxy
        or a DatablockProxy with an Delta item per added, deleted or updated property. One expect only DeltaUpdate,
        although DeltalAddition or DeltaDeletion may be produced when an addon is loaded or unloaded while
        a room is joined. This situation is not really supported as there is no handler to track
        addon changes.

        Args:
            attribute: the struct to update (e.g. a Material instance)
            key: the key that identifies attribute in parent (e.g "Material")
            prop: the Property of struct as found in its enclosing object
            context: proxy and visit state
        """

        # Create a proxy that will be populated with attributes differences.
        diff = self.__class__()
        diff.init(attribute)
        delta = self._diff(attribute, key, prop, context, diff)
        return delta

    def _diff(
        self, attribute: T.bpy_struct, key: Union[int, str], prop: T.Property, context: Context, diff: StructProxy
    ) -> Optional[Delta]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state
        and attached the difference to diff.

        See diff()

        Args:
            attribute: the struct to update (e.g. a Material instance)
            key: the key that identifies attribute in parent (e.g "Material")
            prop: the Property of struct as found in its enclosing object
            context: proxy and visit state
            diff: the proxy that holds the difference and will be transmitted in a Delta

        Returns:
            a delta if any difference is found, None otherwise
        """
        # PERF accessing the properties from the synchronized_properties is **far** cheaper that iterating over
        # _data and the getting the properties with
        #   member_property = struct.bl_rna.properties[k]
        # line to which py-spy attributes 20% of the total diff !
        if prop is not None:
            context.visit_state.path.append(key)
        try:
            properties = context.synchronized_properties.properties(attribute)
            properties = specifics.conditional_properties(attribute, properties)
            for k, member_property in properties:
                # TODO in test_differential.StructDatablockRef.test_remove
                # target et a scene, k is world and v (current world value) is None
                # so diff fails. v should be a BpyIDRefNoneProxy

                # make a difference between None value and no member
                try:
                    member = getattr(attribute, k)
                except AttributeError:
                    logger.info(f"diff: unknown attribute {k} in {attribute}")
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
