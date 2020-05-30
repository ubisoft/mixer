import logging
from typing import Mapping, List, Tuple, Any

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.proxy import (
    BpyBlendProxy,
    BpyIDProxy,
    BpyStructProxy,
    BpyPropDataCollectionProxy,
    ensure_uuid,
    Proxy,
)
from mixer.blender_data.filter import Context

logger = logging.Logger(__name__, logging.INFO)

Uuid = str
BlendDataCollectionName = str
Name = str

ItemsAdded = Mapping[Name, T.bpy_prop_collection]
ItemsRemoved = List[Name]
ItemsRenamed = List[Tuple[Name, Name]]
ItemsUpdated = Mapping[Name, "BpyIDDiff"]


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
    removed_items = [proxy_items[uuid] for uuid in removed_uuids]
    renamed_items = [(proxy_items[uuid], blender_items[uuid][0]) for uuid in renamed_uuids]

    return added_items, removed_items, renamed_items


class BpyDiff:
    pass


class BpyStructDiff(BpyDiff):
    deltas: {Name, Any} = {}

    def diff(self, proxy: BpyStructProxy, bl_struct: T.bpy_struct):
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


class BpyPropCollectionDiff(BpyDiff):
    """
    Diff for a bpy_prop_collection. May not work as is for bpy_prop_collection not in bpy.data
    """

    items_added: ItemsAdded = {}
    items_removed: ItemsRemoved = []
    items_renamed: ItemsRenamed = []

    def diff(self, proxy: BpyPropDataCollectionProxy, bl_collection: T.bpy_prop_collection, context: Context):
        self.items_added.clear()
        self.items_removed.clear()
        self.items_renamed.clear()
        blender_items = {}
        for name, item in bl_collection.items():
            # TODO dot it here or in Proxy ?
            ensure_uuid(item)
            blender_items[item.mixer_uuid] = (name, bl_collection)
        proxy_items = {item.mixer_uuid: name for name, item in proxy._data.items()}
        self.items_added, self.items_removed, self.items_renamed = find_renamed(proxy_items, blender_items)

    def empty(self):
        return not (self.items_added or self.items_removed or self.items_renamed)


class BpyBlendDiff(BpyDiff):
    """
    Diff for the whole bpy.data
    """

    collection_deltas: Mapping[BlendDataCollectionName, BpyPropCollectionDiff] = {}
    id_deltas: List[Tuple[BpyIDProxy, T.ID]] = []

    def diff(self, blend_proxy: BpyBlendProxy, context: Context):
        self.collection_deltas.clear()
        self.id_deltas.clear()

        for name, _ in context.properties(bpy_type=T.BlendData):
            collection = getattr(bpy.data, name)
            delta = BpyPropCollectionDiff()
            delta.diff(blend_proxy._data[name], collection, context)
            if not delta.empty():
                self.collection_deltas[name] = delta
