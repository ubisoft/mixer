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
Utility proxy classes

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING, List, Set, Tuple, Union

import bpy.types as T  # noqa

from mixer.blender_data.attributes import write_attribute
from mixer.blender_data.json_codec import serialize
from mixer.blender_data.proxy import Delta, DeltaReplace, DeltaUpdate, Proxy
from mixer.blender_data.struct_proxy import StructProxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


@serialize
class SetProxy(Proxy):
    """Proxy for sets of primitive types

    Found in DecimateModifier.delimit
    """

    _serialize = ("_items",)

    def __init__(self):
        self._items: List[Any] = []

    @property
    def items(self):
        return self._items

    @items.setter
    def items(self, value):
        self._items = list(value)
        self._items.sort()

    def load(self, attribute: Set[Any]) -> SetProxy:
        """
        Load the attribute Blender struct into this proxy

        Args:
            attribute: the Blender set to load into this proxy
        """
        self.items = attribute
        return self

    def save(
        self,
        attribute: Set[Any],
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        context: Context,
    ):
        """Save this proxy into attribute, which is contained in parent[key] or parent.key

        Args:
            attribute: the attribute into which the proxy is saved.
            parent: the attribute that contains attribute
            key: the string or index that identifies attribute in parent
        """
        try:
            if isinstance(key, int):
                parent[key] = set(self.items)
            else:
                setattr(parent, key, set(self.items))
        except Exception as e:
            logger.error("SetProxy.save(): exception for attribute ...")
            logger.error(f"... {context.visit_state.display_path()}.{key}...")
            logger.error(f"... {e!r}")

    def apply(
        self,
        attribute: Any,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> Proxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the Blender attribute to update
            parent: the attribute that contains attribute
            key: the key that identifies attribute in parent
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """
        assert isinstance(delta, DeltaReplace)
        self.items = delta.value.items
        if to_blender:
            self.save(attribute, parent, key, context)
        return self

    def diff(
        self, attribute: Set[Any], unused_key: Union[int, str], unused_prop: T.Property, unused_context: Context
    ) -> Optional[Delta]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        Args:
            attribute: the set to update (e.g. a the "delimit" attribute of a DecimateModifier instance)
            unused_key: the key that identifies attribute in parent (e.g "delimit")
            unused_prop: the Property of attribute as found in its parent attribute
            unused_context: proxy and visit state
        """
        if set(self.items) == attribute:
            return None

        new_set = SetProxy()
        new_set.items = attribute
        return DeltaReplace(new_set)


@serialize
class CustomPropertiesProxy:
    """Proxy-like for datablock Custom Properties"""

    _serialize = ("_dict", "_rna_ui")

    def __init__(self):
        self._dict = {}
        """Custom properties and their values"""

        self._rna_ui = {}
        """_RNA_UI dictionnary"""

    def _user_keys(self, datablock: T.ID):
        keys = set(datablock.keys())
        rna_ui = datablock.get("_RNA_UI", None)
        keys -= {"_RNA_UI"}
        keys -= set(datablock.bl_rna.properties.keys())
        return keys, rna_ui

    def load(self, datablock: T.ID):
        """Load the custom properties of datablock, skipping API defined properties"""
        keys, rna_ui = self._user_keys(datablock)
        # This only load custom properties with a UI
        if rna_ui is None:
            self._dict.clear()
            self._rna_ui.clear()
            return self

        self._rna_ui = rna_ui.to_dict()
        self._dict = {name: datablock.get(name) for name in keys}

    def save(self, datablock: T.ID):
        """Overwrite all the custom properties in datablock, including the UI"""
        if self._rna_ui:
            datablock["_RNA_UI"] = self._rna_ui
        else:
            try:
                del datablock["_RNA_UI"]
            except KeyError:
                pass

        current_keys, _ = self._user_keys(datablock)
        remove = current_keys - set(self._dict.keys())
        for key in remove:
            del datablock[key]
        for key, value in self._dict.items():
            datablock[key] = value

    def diff(self, datablock: T.ID) -> Optional[CustomPropertiesProxy]:
        current = CustomPropertiesProxy()
        current.load(datablock)
        if self._dict == current._dict and self._rna_ui == current._rna_ui:
            return None

        return current

    def apply(self, datablock: T.ID, update: Optional[CustomPropertiesProxy], to_blender: bool):
        if update is None:
            return

        self._rna_ui = update._rna_ui
        self._dict = update._dict
        if to_blender:
            self.save(datablock)


@serialize
class PtrToCollectionItemProxy(Proxy):
    """Proxy for an attribute that contains a pointer into a bpy_prop_collection in the same embeddded datablock.

    For instance, ShapeKey.relative_key is a pointer to a Key.key_blocks element.
    """

    _serialize = ("_path", "_index")

    _ctors = {(T.ShapeKey, "relative_key"): ("key_blocks",), (T.FCurve, "group"): ("groups",)}
    """ { struct member: path to the enclosing datablock collection}"""

    @classmethod
    def make(cls, attr_type: type, key: str) -> Optional[PtrToCollectionItemProxy]:
        try:
            collection_path = cls._ctors[(attr_type, key)]
        except KeyError:
            return None
        return cls(collection_path)

    def __init__(self, path: Tuple[Union[int, str]] = ()):
        self._path: Tuple[Union[int, str]] = path
        """Path of the collection that contains the pointed to item in the enclosing standalone datablock."""

        self._index: int = -1
        """Index in the collection identified by _path, -1 if ot present"""

    def __bool__(self):
        return self._index != -1

    def _collection(self, datablock) -> T.bpy_prop_collection:
        """Returns the bpy_prop_collection that contains the pointees referenced by the attribute managed by this proxy
        (e.g. returns Key.key_blocks, if this proxy manages Skape_key.relative_key)."""
        collection = datablock
        for i in self._path:
            try:
                collection = getattr(collection, i)
            except (TypeError, AttributeError):
                collection = collection[i]

        return collection

    def _compute_index(self, attribute: T.bpy_struct):
        """Returns the index in the pointee bpy_prop_collection (e.g Key.key_blocks) that contains the item referenced
        by the attribute managed by this proxy (e.g ShapeKey.relative_key)."""
        collection = self._collection(attribute.id_data)
        for index, item in enumerate(collection):
            if item == attribute:
                return index
        return -1

    def load(self, attribute: T.bpy_struct) -> PtrToCollectionItemProxy:
        """
        Load the pointer member (e.g relative_key) of the attribute managed by this proxy (e.g. a ShapeKey in
        Key.key_blocks).

        Args:
            attribute: the struct that contains the pointer
        """
        self._index = self._compute_index(attribute)
        return self

    def save(
        self,
        attribute: T.bpy_struct,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        context: Context,
    ):
        """Save this proxy into attribute, which is contained in parent[key] or parent.key

        Args:
            attribute: the attribute into which the proxy is saved.
            parent: the attribute that contains attribute
            key: the string or index that identifies attribute in parent
            context: proxy and visit state
        """
        collection = self._collection(attribute.id_data)
        pointee = collection[self._index]
        write_attribute(parent, key, pointee, context)

    def apply(
        self,
        attribute: Any,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> Proxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the Blender attribute to update
            parent: the attribute that contains attribute
            key: the key that identifies attribute in parent
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """
        self._index = delta.value._index
        if to_blender:
            self.save(attribute, parent, key, context)
        return self

    def diff(
        self, attribute: T.bpy_struct, unused_key: str, unused_prop: T.Property, unused_context: Context
    ) -> Optional[Delta]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        Args:
            attribute: the attribute (e.g a ShapeKey) that contains the member managed by the proxy  (e.g. relative_key)
            unused_key: the name of the attribute member that is managed by this proxy (e.g. relative_key)
            unused_prop: the Property of attribute as found in its parent attribute
            unused_context: proxy and visit state
        """
        index = self._compute_index(attribute)
        if index == self._index:
            return None

        update = PtrToCollectionItemProxy()
        update._index = index
        return DeltaUpdate(update)
