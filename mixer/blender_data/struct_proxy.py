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

from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.proxy import DeltaUpdate, Proxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import VisitState

logger = logging.getLogger(__name__)


class StructProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    # TODO limit depth like in multiuser. Anyhow, there are circular references in f-curves
    def __init__(self):

        # We care for some non readonly properties. Collection object are tagged read_only byt can be updated with

        # Beware :

        # >>> bpy.types.Scene.bl_rna.properties['collection']
        # <bpy_struct, PointerProperty("collection")>

        # TODO is_readonly may be only interesting for "base types". FOr Collections it seems always set to true
        # meaning that the collection property slot cannot be updated although the object is mutable
        # TODO we also care for some readonly properties that are in fact links to data collections

        # The property information are taken from the containing class, not from the attribute.
        # So we get :
        #   T.Scene.bl_rna.properties['collection']
        #       <bpy_struct, PointerProperty("collection")>
        #   T.Scene.bl_rna.properties['collection'].fixed_type
        #       <bpy_struct, Struct("Collection")>
        # But if we take the information in the attribute we get information for the dereferenced
        # data
        #   D.scenes[0].collection.bl_rna
        #       <bpy_struct, Struct("Collection")>
        #
        # We need the former to make a difference between T.Scene.collection and T.Collection.children.
        # the former is a pointer
        self._data = {}
        pass

    def load(self, bl_instance: any, visit_state: VisitState):

        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        properties = visit_state.context.properties(bl_instance)
        # includes properties from the bl_rna only, not the "view like" properties like MeshPolygon.edge_keys
        # that we do not want to load anyway
        properties = specifics.conditional_properties(bl_instance, properties)
        for name, bl_rna_property in properties:
            attr = getattr(bl_instance, name)
            attr_value = read_attribute(attr, bl_rna_property, visit_state)
            # Also write None values. We use them to reset attributes like Camera.dof.focus_object
            self._data[name] = attr_value
        return self

    def save(self, bl_instance: Any, key: Union[int, str], visit_state: VisitState):
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
                target = specifics.add_element(self, bl_instance, key, visit_state)
        else:
            specifics.pre_save_struct(self, bl_instance, key)
            target = getattr(bl_instance, key, None)

        if target is None:
            if isinstance(bl_instance, T.bpy_prop_collection):
                logger.warning(f"Cannot write to '{bl_instance}', attribute '{key}' because it does not exist.")
                logger.warning("Note: Not implemented write to dict")
            else:
                # Don't log this because it produces too many log messages when participants have plugins
                # f"Note: May be due to a plugin used by the sender and not on this Blender"
                # f"Note: May be due to unimplemented 'use_{key}' implementation for type {type(bl_instance)}"
                # f"Note: May be {bl_instance}.{key} should not have been saved"
                pass

            return

        for k, v in self._data.items():
            write_attribute(target, k, v, visit_state)

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        struct_delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> StructProxy:
        """
        Apply diff to the Blender attribute at parent[key] or parent.key and update accordingly this proxy entry
        at key.

        Args:
            parent ([type]): [description]
            key ([type]): [description]
            delta ([type]): [description]
            visit_state ([type]): [description]

        Returns:
            [type]: [description]
        """
        if struct_delta is None:
            return

        assert isinstance(key, (int, str))

        # TODO factozize with save

        if isinstance(key, int):
            struct = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            struct = parent.get(key)
            if struct is None:
                struct = specifics.add_element(self, parent, key, visit_state)
        else:
            specifics.pre_save_struct(self, parent, key)
            struct = getattr(parent, key, None)

        struct_update = struct_delta.value
        assert type(struct_update) == type(self)
        for k, member_delta in struct_update._data.items():
            try:
                current_value = self._data.get(k)
                self._data[k] = apply_attribute(struct, k, current_value, member_delta, visit_state, to_blender)
            except Exception as e:
                logger.warning(f"StructLike.apply(). Processing {member_delta}")
                logger.warning(f"... for {struct}.{k}")
                logger.warning(f"... Exception: {e}")
                logger.warning("... Update ignored")
                continue
        return self

    def diff(self, struct: T.Struct, _: T.Property, visit_state: VisitState) -> Optional[DeltaUpdate]:
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

        # PERF accessing the properties from the context is **far** cheaper that iterating over
        # _data and the getting the properties with
        #   member_property = struct.bl_rna.properties[k]
        # line to which py-spy attributes 20% of the total diff !

        for k, member_property in visit_state.context.properties(struct):
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
            delta = diff_attribute(member, member_property, proxy_data, visit_state)
            if delta is not None:
                diff._data[k] = delta

        # if anything has changed, wrap the hollow proxy in a DeltaUpdate. This may be superfluous but
        # it is homogenous with additions and deletions
        if len(diff._data):
            return DeltaUpdate(diff)

        return None
