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
from typing import List, Optional, Tuple, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.proxy import Delta, DeltaAddition, DeltaReplace, DeltaUpdate
from mixer.blender_data.proxy import Proxy
from mixer.blender_data.struct_proxy import StructProxy

if TYPE_CHECKING:
    from mixer.blender_data.datablock_proxy import DatablockProxy
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


def _proxy_factory(attr):
    if isinstance(attr, T.ID) and not attr.is_embedded_data:
        from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy

        return DatablockRefProxy()
    elif attr is None:
        from mixer.blender_data.misc_proxies import NonePtrProxy

        return NonePtrProxy()
    else:
        return StructProxy()


class StructCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of non-datablock Struct.

    It can track an array (int keys) or a dictionnary(string keys). Both implementation are
    in the same class as it is not possible to know at creation time the type of an empty collection
    """

    _serialize = ("_sequence", "_diff_additions", "_diff_deletions", "_diff_updates")

    def __init__(self):
        # TODO remove _data, just here to make JsonCodec happy
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

    def __len__(self):
        return len(self._sequence)

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

        context.visit_state.path.append(key)
        try:
            self._sequence = [_proxy_factory(v).load(v, i, context) for i, v in enumerate(bl_collection.values())]
        finally:
            context.visit_state.path.pop()
        return self

    def save(self, collection: T.bpy_prop_collection, parent: T.bpy_struct, key: str, context: Context):
        """
        Save this proxy into collection

        Args:
            collection: the collection into which this proxy is saved
            parent: the attribute that contains collection (e.g. a Scene instance)
            key: the name of the collection in parent (e.g "background_images")
            context: the proxy and visit state
        """
        context.visit_state.path.append(key)
        try:
            sequence = self._sequence
            specifics.truncate_collection(collection, len(self._sequence))
            for i in range(len(collection), len(sequence)):
                item_proxy = sequence[i]
                specifics.add_element(collection, item_proxy, context)
            for i, v in enumerate(sequence):
                write_attribute(collection, i, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self,
        collection: T.bpy_prop_collection,
        parent: T.bpy_struct,
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender=True,
    ) -> StructCollectionProxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the collection to update (e.g. a_mesh.material)
            parent: the attribute that contains attribute (e.g. a a Mesh instance)
            key: the key that identifies attribute in parent (e.g "materials")
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """
        assert isinstance(key, str)

        update = delta.value
        assert type(update) == type(self)

        if isinstance(delta, DeltaReplace):
            self._sequence = update._sequence
            if to_blender:
                specifics.truncate_collection(collection, 0)
                self.save(collection, parent, key, context)
        else:
            # a sparse update

            context.visit_state.path.append(key)
            try:
                sequence = self._sequence

                # Delete before update and process updates in reverse order to avoid spurious renames.
                # Starting with sequence A, B, C, D and delete B causes :
                # - an update for items 1 and 2 to be renamed into C and D
                # - one delete
                # If the update is processed first, Blender renames item 3 into D.001
                # If the deletes are processed first but the updates are processed in order, Blender renames item 1
                # into C.001

                delete_count = update._diff_deletions
                if delete_count > 0:
                    if to_blender:
                        specifics.truncate_collection(collection, len(collection) - delete_count)
                    del sequence[-delete_count:]

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
    ) -> Optional[Union[DeltaUpdate, DeltaReplace]]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        This proxy tracks a collection of items indexed by string (e.g Scene.render.views) or int.
        The result will be a ProxyDiff that contains a Delta item per added, deleted or updated item

        Args:
            collection; the collection that must be diffed agains this proxy
            key: the name of the collection, to record in the visit path
            collection_property; the property os collection as found in its enclosing object
        """
        sequence = self._sequence
        if len(sequence) == 0 and len(collection) == 0:
            return None

        if specifics.diff_must_replace(collection, sequence, collection_property):
            # A collection cannot be updated because either:
            # - some of its members cannot be updated :
            #   SplineBezierPoints has no API to remove points, so Curve.splines cannot be update and must be replaced
            # - updating the name of members will cause unsolicited renames.
            #   When swapping layers A and B in a GreasePencilLayers, renaming layer 0 into B cause an unsolicited
            #   rename of layer 0 into B.001
            # Send a replacement for the whole collection
            self.load(collection, key, collection_property, context)
            return DeltaReplace(self)
        else:
            item_property = collection_property.fixed_type
            context.visit_state.path.append(key)
            try:
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
