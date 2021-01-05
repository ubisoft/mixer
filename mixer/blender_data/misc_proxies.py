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
from typing import Any, Optional, TYPE_CHECKING, List, Set, Union

import bpy.types as T  # noqa

from mixer.blender_data.attributes import read_attribute
from mixer.blender_data.proxy import Delta, DeltaReplace, DeltaUpdate, Proxy
from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class NonePtrProxy(Proxy):
    """Proxy for a None PointerProperty value.

    When setting a PointerProperty from None to a valid reference, apply_attributs requires that
    the proxyfied value implements apply().

    This is used for Pointers to standalone datablocks like Scene.camera.

    TODO Check it it is meaningfull for anything else ?
    """

    def target(self, context: Context) -> None:
        return None

    @property
    def mixer_uuid(self) -> str:
        return "00000000-0000-0000-0000-000000000000"

    def load(self, *_):
        return self

    def save(self, unused_attribute, parent: T.bpy_struct, key: Union[int, str], context: Context):
        """Save None into parent.key or parent[key]"""

        if isinstance(key, int):
            parent[key] = None
        else:
            try:
                setattr(parent, key, None)
            except AttributeError as e:
                # Motsly errors like
                #   AttributeError: bpy_struct: attribute "node_tree" from "Material" is read-only
                # Avoiding them would require filtering attrivutes on save in order not to set
                # Material.node_tree if Material.use_nodes is False
                logger.debug("NonePtrProxy.save() exception for {parent}[{key}]...")
                logger.debug(f"... {repr(e)}")

    def apply(
        self,
        attribute: Union[T.bpy_struct, T.bpy_prop_collection],
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> Union[DatablockRefProxy, NonePtrProxy]:
        """
        Apply delta to an attribute with None value.

        This is used for instance Scene.camera is None and updatde to hold a valid Camera reference

        Args:
            attribute: the Blender attribute to update (e.g a_scene.camera)
            parent: the attribute that contains attribute (e.g. a Scene instance)
            key: the key that identifies attribute in parent (e.g; "camera").
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update attribute in addition to this Proxy
        """
        update = delta.value

        if isinstance(update, DatablockRefProxy):
            if to_blender:
                datablock = context.proxy_state.datablocks.get(update._datablock_uuid)
                if isinstance(key, int):
                    parent[key] = datablock
                else:
                    setattr(parent, key, datablock)
            return update

        # A none PointerProperty that can point to something that is not a datablock.
        # Can this happen ?
        logger.error(f"apply({parent}, {key}) called with a {type(update)} at {context.visit_state.path}")
        return self

    def diff(
        self,
        container: Union[T.bpy_prop_collection, T.Struct],
        key: Union[str, int],
        prop: T.Property,
        context: Context,
    ) -> Optional[DeltaUpdate]:
        attr = read_attribute(container, key, prop, context)
        if isinstance(attr, NonePtrProxy):
            return None
        return DeltaUpdate(attr)


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
            logger.error(f"SetProxy.save() at {parent}.{key}. Exception ...")
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
