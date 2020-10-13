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

import itertools
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.attributes import apply_attribute, diff_attribute, read_attribute, write_attribute
from mixer.blender_data.proxy import DeltaAddition, DeltaDeletion, DeltaUpdate
from mixer.blender_data.proxy import MIXER_SEQUENCE, Proxy
from mixer.blender_data.node_proxy import NodeLinksProxy
from mixer.blender_data.struct_proxy import StructProxy

if TYPE_CHECKING:
    from mixer.blender_data.datablock_proxy import DatablockProxy
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


# TODO make these functions generic after enough sequences have been seen
# TODO move to specifics.py
def write_curvemappoints(target, src_sequence, context: Context):
    src_length = len(src_sequence)

    # CurveMapPoints specific (alas ...)
    if src_length < 2:
        logger.error(f"Invalid length for curvemap: {src_length}. Expected at least 2")
        return

    # truncate dst
    while src_length < len(target):
        target.remove(target[-1])

    # extend dst
    while src_length > len(target):
        # .new() parameters are CurveMapPoints specific
        # for CurvemapPoint, we can initialize to anything then overwrite. Not sure this is doable for other types
        # new inserts in head !
        # Not optimal for big arrays, but much simpler given that the new() parameters depend on the collection
        # in a way that cannot be determined automatically
        target.new(0.0, 0.0)

    assert src_length == len(target)
    for i in range(src_length):
        write_attribute(target, i, src_sequence[i], context)


def write_metaballelements(target, src_sequence, context: Context):
    src_length = len(src_sequence)

    # truncate dst
    while src_length < len(target):
        target.remove(target[-1])

    # extend dst
    while src_length > len(target):
        # Creates a BALL, but will be changed by write_attribute
        target.new()

    assert src_length == len(target)
    for i in range(src_length):
        write_attribute(target, i, src_sequence[i], context)


class StructCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of non-datablock Struct.

    It can track an array (int keys) or a dictionnary(string keys). Both implementation are
    in the same class as it is not possible to know at creation time the type of an empty collection
    """

    def __init__(self):
        self._data: Dict[Union[str, int], DatablockProxy] = {}

    @classmethod
    def make(cls, attr_property: T.Property):
        if attr_property.srna == T.NodeLinks.bl_rna:
            return NodeLinksProxy()
        return StructCollectionProxy()

    @property
    def length(self) -> int:
        sequence = self._data.get(MIXER_SEQUENCE)
        if sequence:
            return len(sequence)
        return len(self._data)

    def load(self, bl_collection: T.bpy_prop_collection, bl_collection_property: T.Property, context: Context):

        if len(bl_collection) == 0:
            self._data.clear()
            return self

        try:
            context.visit_state.path.append(bl_collection_property.identifier)
            # no keys means it is a sequence. However bl_collection.items() returns [(index, item)...]
            is_sequence = not bl_collection.keys()
            if is_sequence:
                # easier for the encoder to always have a dict
                self._data = {
                    MIXER_SEQUENCE: [StructProxy().load(v, i, context) for i, v in enumerate(bl_collection.values())]
                }
            else:
                self._data = {k: StructProxy().load(v, k, context) for k, v in bl_collection.items()}
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
            sequence = self._data.get(MIXER_SEQUENCE)
            if sequence:
                srna = bl_instance.bl_rna.properties[attr_name].srna
                if srna:
                    # TODO move to specifics
                    if srna.bl_rna is bpy.types.CurveMapPoints.bl_rna:
                        write_curvemappoints(target, sequence, context)
                    elif srna.bl_rna is bpy.types.MetaBallElements.bl_rna:
                        write_metaballelements(target, sequence, context)
                    elif srna.bl_rna is bpy.types.MeshPolygons.bl_rna:
                        # see soable_collection_properties
                        target.add(len(sequence))
                        for i, proxy in enumerate(sequence):
                            write_attribute(target, i, proxy, context)
                    elif srna.bl_rna is bpy.types.GPencilFrames.bl_rna:
                        for i, proxy in enumerate(sequence):
                            frame_number = proxy.data("frame_number")
                            target.new(frame_number)
                            write_attribute(target, i, proxy, context)
                    elif srna.bl_rna is bpy.types.GPencilStrokes.bl_rna:
                        for i, proxy in enumerate(sequence):
                            target.new()
                            write_attribute(target, i, proxy, context)
                    elif srna.bl_rna is bpy.types.GPencilStrokePoints.bl_rna:
                        target.new(len(sequence))
                        for i, proxy in enumerate(sequence):
                            write_attribute(target, i, proxy, context)
                    else:
                        logger.error(f"unsupported sequence type {srna}")
                        pass

                elif len(target) == len(sequence):
                    for i, v in enumerate(sequence):
                        # TODO this way can only save items at pre-existing slots. The bpy_prop_collection API
                        # uses struct specific API and ctors:
                        # - CurveMapPoints uses: .new(x, y) and .remove(point), no .clear(). new() inserts in head !
                        #   Must have at least 2 points left !
                        # - NodeTreeOutputs uses: .new(type, name), .remove(socket), has .clear()
                        # - ActionFCurves uses: .new(data_path, index=0, action_group=""), .remove(fcurve)
                        # - GPencilStrokePoints: .add(count), .pop()
                        write_attribute(target, i, v, context)
                else:
                    logger.warning(
                        f"Not implemented: write sequence of different length (incoming: {len(sequence)}, existing: {len(target)})for {bl_instance}.{attr_name}"
                    )
            else:
                # dictionary
                specifics.truncate_collection(target, self, context)
                for k, v in self._data.items():
                    write_attribute(target, k, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self, parent: Any, key: Union[int, str], delta: Optional[DeltaUpdate], context: Context, to_blender=True
    ) -> StructProxy:

        assert isinstance(key, (int, str))

        # TODO factorize with save

        if isinstance(key, int):
            collection = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            collection = parent.get(key)
            if collection is None:
                collection = specifics.add_element(self, parent, key, context)
        else:
            specifics.pre_save_struct(self, parent, key)
            collection = getattr(parent, key, None)

        update = delta.value
        assert type(update) == type(self)

        try:
            context.visit_state.path.append(key)
            sequence = self._data.get(MIXER_SEQUENCE)
            if sequence:

                # input validity assertions
                add_indices = [i for i, delta in enumerate(update._data.values()) if isinstance(delta, DeltaAddition)]
                del_indices = [i for i, delta in enumerate(update._data.values()) if isinstance(delta, DeltaDeletion)]
                if add_indices or del_indices:
                    # Cannot have deletions and additions
                    assert not add_indices or not del_indices, "not add_indices or not del_indices"
                    indices = add_indices if add_indices else del_indices
                    # Check that adds and deleted are at the end
                    assert (
                        not indices or indices[-1] == len(update._data) - 1
                    ), "not indices or indices[-1] == len(update._data) - 1"
                    # check that adds and deletes are contiguous
                    assert all(
                        a + 1 == b for a, b in zip(indices, iter(indices[1:]))
                    ), "all(a + 1 == b for a, b in zip(indices, iter(indices[1:])))"

                for k, delta in update._data.items():
                    i = int(k)
                    try:
                        if isinstance(delta, DeltaUpdate):
                            sequence[i] = apply_attribute(collection, i, sequence[i], delta, context, to_blender)
                        elif isinstance(delta, DeltaDeletion):
                            if to_blender:
                                item = collection[i]
                                collection.remove(item)
                            del sequence[i]
                        else:  # DeltaAddition
                            # TODO pre save for use_curves
                            # since ordering does not include this requirement
                            if to_blender:
                                raise NotImplementedError("Not implemented: DeltaAddition for array")
                                write_attribute(collection, i, delta.value, context)
                            sequence.append(delta.value)

                    except Exception as e:
                        logger.warning(f"StructCollectionProxy.apply(). Processing {delta}")
                        logger.warning(f"... for {collection}[{i}]")
                        logger.warning(f"... Exception: {e}")
                        logger.warning("... Update ignored")
                        continue
            else:
                for k, delta in update._data.items():
                    try:
                        if isinstance(delta, DeltaDeletion):
                            # TODO do all collections have remove ?
                            # see "name collision" in diff()
                            k = k[1:]
                            if to_blender:
                                item = collection[k]
                                collection.remove(item)
                            del self._data[k]
                        elif isinstance(delta, DeltaAddition):
                            # TODO pre save for use_curves
                            # since ordering does not include this requirement

                            # see "name collision" in diff()
                            k = k[1:]
                            if to_blender:
                                write_attribute(collection, k, delta.value, context)
                            self._data[k] = delta.value
                        else:
                            self._data[k] = apply_attribute(collection, k, self._data[k], delta, context, to_blender)
                    except Exception as e:
                        logger.warning(f"StructCollectionProxy.apply(). Processing {delta}")
                        logger.warning(f"... for {collection}[{k}]")
                        logger.warning(f"... Exception: {e}")
                        logger.warning("... Update ignored")
                        continue
        finally:
            context.visit_state.path.pop()

        return self

    def diff(
        self, collection: T.bpy_prop_collection, collection_property: T.Property, context: Context
    ) -> Optional[DeltaUpdate]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        This proxy tracks a collection of items indexed by string (e.g Scene.render.views) or int.
        The result will be a ProxyDiff that contains a Delta item per added, deleted or updated item

        Args:
            collection; the collection that must be diffed agains this proxy
            collection_property; the property os collection as found in its enclosing object
        """

        diff = self.__class__()
        item_property = collection_property.fixed_type
        try:
            context.visit_state.path.append(collection_property.identifier)
            sequence = self._data.get(MIXER_SEQUENCE)
            if sequence:
                # indexed by int
                # TODO This produces one DeltaDeletion by removed item. Produce a range in case may items are
                # deleted

                # since the diff sequence is hollow, we cannot store it in a list. Use a dict with int keys instead
                for i, (proxy_value, blender_value) in enumerate(itertools.zip_longest(sequence, collection)):
                    if proxy_value is None:
                        value = read_attribute(collection[i], item_property, context)
                        diff._data[i] = DeltaAddition(value)
                    elif blender_value is None:
                        diff._data[i] = DeltaDeletion(self.data(i))
                    else:
                        delta = diff_attribute(collection[i], item_property, proxy_value, context)
                        if delta is not None:
                            diff._data[i] = delta
            else:
                # index by string. This is similar to DatablockCollectionProxy.diff
                # Renames are detected as Deletion + Addition

                # This assumes that keys ordring is the same in the proxy and in blender, which is
                # guaranteed by the fact that proxy load uses SynchronizedProperties.properties()

                bl_rna = getattr(collection, "bl_rna", None)
                if bl_rna is not None and isinstance(
                    bl_rna, (type(T.ObjectModifiers.bl_rna), type(T.ObjectGpencilModifiers))
                ):
                    # TODO move this into specifics.py
                    # order-dependant collections with different types like Modifiers
                    proxy_names = list(self._data.keys())
                    blender_names = collection.keys()
                    proxy_types = [self.data(name).data("type") for name in proxy_names]
                    blender_types = [collection[name].type for name in blender_names]
                    if proxy_types == blender_types and proxy_names == blender_names:
                        # Same types and names : do sparse modification
                        for name in proxy_names:
                            delta = diff_attribute(collection[name], item_property, self.data(name), context)
                            if delta is not None:
                                diff._data[name] = delta
                    else:
                        # names or types do not match, rebuild all
                        # There are name collisions during Modifier order change for instance, so prefix
                        # the names to avoid them (using a tuple fails in the json encoder)
                        for name in proxy_names:
                            diff._data["D" + name] = DeltaDeletion(self.data(name))
                        for name in blender_names:
                            value = read_attribute(collection[name], item_property, context)
                            diff._data["A" + name] = DeltaAddition(value)
                else:
                    # non order dependant, uniform types
                    proxy_keys = self._data.keys()
                    blender_keys = collection.keys()
                    added_keys = blender_keys - proxy_keys
                    for k in added_keys:
                        value = read_attribute(collection[k], item_property, context)
                        diff._data["A" + k] = DeltaAddition(value)

                    deleted_keys = proxy_keys - blender_keys
                    for k in deleted_keys:
                        diff._data["D" + k] = DeltaDeletion(self.data(k))

                    maybe_updated_keys = proxy_keys & blender_keys
                    for k in maybe_updated_keys:
                        delta = diff_attribute(collection[k], item_property, self.data(k), context)
                        if delta is not None:
                            diff._data[k] = delta
        finally:
            context.visit_state.path.pop()

        if len(diff._data):
            return DeltaUpdate(diff)

        return None

    def find(self, path: List[Union[int, str]]) -> Proxy:
        if not path:
            return self

        head, *tail = path
        return self._data[head].find(tail)
