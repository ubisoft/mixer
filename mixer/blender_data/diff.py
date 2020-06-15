import logging
from typing import Any, List, Mapping, Tuple, TypeVar

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.filter import Context
from mixer.blender_data.proxy import (
    BpyBlendProxy,
    BpyIDProxy,
    BpyStructProxy,
    BpyPropDataCollectionProxy,
    ensure_uuid,
    Proxy,
)

logger = logging.Logger(__name__, logging.INFO)

Uuid = str
BlendDataCollectionName = str
Name = str
BpyIDDiff = TypeVar("BpyIDDiff")
# Item name : collection name
ItemsAdded = Mapping[Name, Name]
ItemsRemoved = List[Tuple[Name, Uuid]]
ItemsRenamed = List[Tuple[Name, Name]]
ItemsUpdated = Mapping[Name, BpyIDDiff]


def find_renamed(
    proxy_items: Mapping[Uuid, Name], blender_items: Mapping[Uuid, Tuple[Name, T.bpy_prop_collection]]
) -> Tuple[ItemsAdded, ItemsRemoved, ItemsRenamed]:
    """
    Split before/after mappings into added/removed/renamed

    Rename detection is based on the mapping keys (e.g. uuids)
    """
    proxy_uuids = set(proxy_items.keys())
    blender_uuids = set(blender_items.keys())

    renamed_uuids = {uuid for uuid in blender_uuids & proxy_uuids if proxy_items[uuid] != blender_items[uuid][0]}
    added_uuids = blender_uuids - proxy_uuids - renamed_uuids
    removed_uuids = proxy_uuids - blender_uuids - renamed_uuids

    added_items = {blender_items[uuid][0]: blender_items[uuid][1] for uuid in added_uuids}
    removed_items = [(proxy_items[uuid], uuid) for uuid in removed_uuids]
    renamed_items = [(proxy_items[uuid], blender_items[uuid][0]) for uuid in renamed_uuids]

    return added_items, removed_items, renamed_items


class BpyDiff:
    pass


class BpyStructDiff(BpyDiff):
    """Perform a diff between a BpyStructProxy and a Blender item.

    Provides a result that can be used to update the proxy and can also be serialized
    """

    deltas: {Name, Any} = {}

    def diff(self, proxy: BpyStructProxy, bl_struct: T.bpy_struct):

        # TODO untested draft

        self.deltas.clear()
        # updated only, suppose the names are the same
        # peoperties have already been filtered when loading the proxy, so use the
        # proxy keys. This probably misses new properties loaded from a plugin
        for attr_name, proxy_value in proxy._data.items():
            bl_value = getattr(bl_struct, attr_name)
            proxy_value = BpyStructProxy.read(attr_name)
            if issubclass(proxy_value, Proxy):
                # TODO find the Differ
                pass
            else:
                # TODO optimize for arrays
                if proxy_value != bl_value:
                    self.deltas[attr_name] = (proxy_value, bl_value)


class BpyIDDiff(BpyStructDiff):
    def diff(self, proxy: BpyIDProxy, bl_id: T.ID):
        # if is a struct otherwise(collection, array, ...)
        super().diff(proxy, bl_id)


excluded_names = ["__last_scene_to_be_removed__"]


class BpyPropCollectionDiff(BpyDiff):
    """
    Diff for a bpy_prop_collection. May not work as is for bpy_prop_collection not in bpy.data
    """

    items_added: ItemsAdded = {}
    items_removed: ItemsRemoved = []
    items_renamed: ItemsRenamed = []

    def diff(self, proxy: BpyPropDataCollectionProxy, collection_name: str, context: Context):
        self.items_added.clear()
        self.items_removed.clear()
        self.items_renamed.clear()
        bl_collection = getattr(bpy.data, collection_name)
        blender_items = {}
        for name, item in bl_collection.items():
            if name in excluded_names:
                continue
            # TODO dot it here or in Proxy ?
            ensure_uuid(item)
            blender_items[item.mixer_uuid] = (name, collection_name)
        proxy_items = {item.mixer_uuid(): name for name, item in proxy._data.items()}
        self.items_added, self.items_removed, self.items_renamed = find_renamed(proxy_items, blender_items)
        if not self.empty():
            BlendData.instance().collection(collection_name).set_dirty()

    def empty(self):
        return not (self.items_added or self.items_removed or self.items_renamed)


class BpyBlendDiff(BpyDiff):
    """
    Diff for the whole bpy.data
    """

    # A list of deltas per bpy.data collection. Use a list bacause if will be sorted later
    collection_deltas: List[Tuple[BlendDataCollectionName, BpyPropCollectionDiff]] = []

    # TODO cleanup: not used.
    # Will not be used as the per_DI deltas will be limited to the depsgraph updates
    id_deltas: List[Tuple[BpyIDProxy, T.ID]] = []

    def diff(self, blend_proxy: BpyBlendProxy, context: Context):
        self.collection_deltas.clear()
        self.id_deltas.clear()

        for collection_name, _ in context.properties(bpy_type=T.BlendData):
            delta = BpyPropCollectionDiff()
            delta.diff(blend_proxy._data[collection_name], collection_name, context)
            if not delta.empty():
                self.collection_deltas.append((collection_name, delta))
