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
Proxy of a bpy.types.Struct collection, excluding bpy.types.ID collections that are implemented
in datablock_collection_proxy.py

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.proxy import DeltaAddition, DeltaUpdate
from mixer.blender_data.proxy import Proxy
from mixer.blender_data.struct_proxy import StructProxy

if TYPE_CHECKING:
    from mixer.blender_data.datablock_proxy import DatablockProxy
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class StructCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of non-datablock Struct.

    It can track an array (int keys) or a dictionnary(string keys). Both implementation are
    in the same class as it is not possible to know at creation time the type of an empty collection
    """

    _serialize = ("_sequence", "_diff_additions", "_diff_deletions", "_diff_updates")

    def __init__(self):
        # remove this
        self._data = {}
        self._diff_updates: List[Tuple[int, DeltaUpdate]] = []
        self._diff_deletions: int = 0
        self._diff_additions: List[DeltaAddition] = []
        self._sequence: List[DatablockProxy] = []

    @classmethod
    def make(cls, attr_property: T.Property):
        if attr_property.srna == T.NodeLinks.bl_rna:
            from mixer.blender_data.node_proxy import NodeLinksProxy

            return NodeLinksProxy()
        return StructCollectionProxy()

    @property
    def length(self) -> int:
        return len(self._sequence)

    def data(self, key: int, resolve_delta=True) -> Optional[Union[DeltaUpdate, DeltaAddition, DatablockProxy]]:
        """Return the data at key, which may be a struct member, a dict value or an array value,

        Args:
            key: Integer or string to be used as index or key to the data
            resolve_delta: If True, and the data is a Delta, will return the delta value
        """

        # shaky and maybe not useful
        length = self.length
        if key < length:
            delta_update = next((delta for i, delta in self._diff_updates if i == key), None)
            if delta_update is None:
                return self._sequence[key]
            if resolve_delta:
                return delta_update.value
            return delta_update
        else:
            try:
                delta_addition = self._diff_additions[key - length]
            except IndexError:
                return None
            if resolve_delta:
                return delta_addition.value
            return delta_addition

    def load(
        self,
        bl_collection: T.bpy_prop_collection,
        key: Union[int, str],
        bl_collection_property: T.Property,
        context: Context,
    ):

        try:
            context.visit_state.path.append(key)
            self._sequence = [StructProxy.make(v).load(v, i, context) for i, v in enumerate(bl_collection.values())]
        finally:
            context.visit_state.path.pop()
        return self

    def save(self, bl_instance: Any, attr_name: str, context: Context):
        """
        Save this proxy the Blender property
        """
        target = getattr(bl_instance, attr_name, None)
        if target is None:
            # # Don't log this, too many messages
            # f"Saving {self} into non existent attribute {bl_instance}.{attr_name} : ignored"
            return
        try:
            context.visit_state.path.append(attr_name)
            sequence = self._sequence
            specifics.truncate_collection(target, len(self._sequence))
            for i in range(len(target), len(sequence)):
                item_proxy = sequence[i]
                specifics.add_element(target, item_proxy, context)
            for i, v in enumerate(sequence):
                write_attribute(target, i, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self, parent: Any, key: Union[int, str], delta: Optional[DeltaUpdate], context: Context, to_blender=True
    ) -> StructCollectionProxy:

        assert isinstance(key, (int, str))

        # TODO factorize with save

        if isinstance(key, int):
            collection = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            collection = parent.get(key)
        else:
            collection = getattr(parent, key, None)

        update = delta.value
        assert type(update) == type(self)

        try:
            context.visit_state.path.append(key)
            sequence = self._sequence

            # Delete before update and proceed updated in reverse order to avoid spurious renames.
            # Starting with sequence A, B, C, D and delete B causes :
            # - an update for items 1 and 2 to be renamed into C and D
            # - one delete
            # If the update is processed first, item 3 will be spuriously renamed into D.001
            # If the deletes are processed first but the updates are processed in order, item 1 will be spuriously
            # renamed into C.001

            # TODO there is a problem with Grease Pencil layers (internal issue #343) :
            # when layers are swapped, saving the name change causes a spurious rename

            for _ in range(update._diff_deletions):
                if to_blender:
                    item = collection[-1]
                    collection.remove(item)
                del sequence[-1]

            for i, delta_update in reversed(update._diff_updates):
                sequence[i] = apply_attribute(collection, i, sequence[i], delta_update, context, to_blender)

            for i, delta_addition in enumerate(update._diff_additions, len(sequence)):
                if to_blender:
                    item_proxy = delta_addition.value
                    specifics.add_element(collection, item_proxy, context)
                    write_attribute(collection, i, item_proxy, context)
                sequence.append(delta_addition.value)

        except Exception as e:
            logger.warning(f"StructCollectionProxy.apply(). Processing {delta}")
            logger.warning(f"... for {collection}")
            logger.warning(f"... Exception: {e!r}")
            logger.warning("... Update ignored")

        finally:
            context.visit_state.path.pop()

        return self

    def diff(
        self, collection: T.bpy_prop_collection, key: Union[int, str], collection_property: T.Property, context: Context
    ) -> Optional[DeltaUpdate]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        This proxy tracks a collection of items indexed by string (e.g Scene.render.views) or int.
        The result will be a ProxyDiff that contains a Delta item per added, deleted or updated item

        Args:
            collection; the collection that must be diffed agains this proxy
            collection_property; the property os collection as found in its enclosing object
        """
        sequence = self._sequence
        if len(sequence) == 0 and len(collection) == 0:
            return None

        item_property = collection_property.fixed_type
        try:
            context.visit_state.path.append(key)

            diff = self.__class__()
            clear_from = specifics.clear_from(collection, sequence)
            for i in range(clear_from):
                delta = diff_attribute(collection[i], i, item_property, sequence[i], context)
                if delta is not None:
                    diff._diff_updates.append((i, delta))

            diff._diff_deletions = len(sequence) - clear_from

            for i, item in enumerate(collection[clear_from:], clear_from):
                value = read_attribute(item, i, item_property, context)
                diff._diff_additions.append(DeltaAddition(value))
        finally:
            context.visit_state.path.pop()

        if diff._diff_updates or diff._diff_deletions or diff._diff_additions:
            return DeltaUpdate(diff)

        return None

    def find(self, path: List[Union[int, str]]) -> Proxy:
        if not path:
            return self

        head, *tail = path
        return self._data[head].find(tail)
