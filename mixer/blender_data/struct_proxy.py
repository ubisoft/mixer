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
from mixer.blender_data.proxy import DeltaUpdate, Proxy

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

    @classmethod
    def make(cls, attr_property):

        # if isinstance(attr_property, T.NodeLink):
        #     from mixer.blender_data.node_proxy import NodeLinkProxy

        #     return NodeLinkProxy()
        return cls()

    def load(self, bl_instance: Any, parent_key: Union[int, str], context: Context):

        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        properties = context.synchronized_properties.properties(bl_instance)
        # includes properties from the bl_rna only, not the "view like" properties like MeshPolygon.edge_keys
        # that we do not want to load anyway
        properties = specifics.conditional_properties(bl_instance, properties)
        try:
            context.visit_state.path.append(parent_key)
            for name, bl_rna_property in properties:
                attr = getattr(bl_instance, name)
                attr_value = read_attribute(attr, name, bl_rna_property, context)

                # Also write None values. We use them to reset attributes like Camera.dof.focus_object
                self._data[name] = attr_value
        finally:
            context.visit_state.path.pop()

        return self

    def save(self, bl_instance: Any, key: Union[int, str], context: Context):
        """
        Save this proxy into a Blender attribute
        """
        assert isinstance(key, (int, str))

        if isinstance(key, int):
            target = bl_instance[key]
        elif isinstance(bl_instance, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            target = bl_instance.get(key)
            if target is None:
                target = specifics.add_element(self, bl_instance, key, context)
        else:
            specifics.pre_save_struct(self, bl_instance, key)
            target = getattr(bl_instance, key, None)

        if target is None:
            if isinstance(bl_instance, T.bpy_prop_collection):
                logger.warning(f"Cannot write to '{bl_instance}', attribute '{key}' because it does not exist.")
            else:
                # Don't log this because it produces too many log messages when participants have plugins
                # f"Note: May be due to a plugin used by the sender and not on this Blender"
                # f"Note: May be due to unimplemented 'use_{key}' implementation for type {type(bl_instance)}"
                # f"Note: May be {bl_instance}.{key} should not have been saved"
                pass

            return

        try:
            context.visit_state.path.append(key)
            for k, v in self._data.items():
                write_attribute(target, k, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        struct_delta: Optional[DeltaUpdate],
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

        # TODO factorize with save

        if isinstance(key, int):
            struct = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            struct = parent.get(key)
            if struct is None:
                struct = specifics.add_element(self, parent, key, context)
        else:
            specifics.pre_save_struct(self, parent, key)
            struct = getattr(parent, key, None)

        struct_update = struct_delta.value
        assert type(struct_update) == type(self)

        try:
            context.visit_state.path.append(key)
            for k, member_delta in struct_update._data.items():
                current_value = self._data.get(k)
                try:
                    self._data[k] = apply_attribute(struct, k, current_value, member_delta, context, to_blender)
                except Exception as e:
                    logger.warning(f"Struct.apply(). Processing {member_delta}")
                    logger.warning(f"... for {struct}.{k}")
                    logger.warning(f"... Exception: {e}")
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
        try:
            if prop is not None:
                context.visit_state.path.append(key)
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
                    logger.warning(f"diff: unknown attribute {k} in {struct}")
                    continue

                proxy_data = self._data.get(k)
                delta = diff_attribute(member, k, member_property, proxy_data, context)

                if delta is not None:
                    diff._data[k] = delta
        finally:
            if prop is not None:
                context.visit_state.path.pop()

        # if anything has changed, wrap the hollow proxy in a DeltaUpdate. This may be superfluous but
        # it is homogenous with additions and deletions
        if len(diff._data):
            return DeltaUpdate(diff)

        return None
