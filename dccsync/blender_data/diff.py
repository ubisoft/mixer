import bpy
import mathutils
from uuid import uuid4
from typing import Mapping, Any


def find_renamed(items_before: Mapping[Any, Any], items_after: Mapping[Any, Any]):
    """
    Split before/after mappings into added/removed/renamed

    Rename detection is based on the mapping keys (e.g. uuids)
    """
    uuids_before = {uuid for uuid in items_before.keys()}
    uuids_after = {uuid for uuid in items_after.keys()}
    renamed_uuids = {uuid for uuid in uuids_after & uuids_before if items_before[uuid] != items_after[uuid]}
    added_items = [items_after[uuid] for uuid in uuids_after - uuids_before - renamed_uuids]
    removed_items = [items_before[uuid] for uuid in uuids_before - uuids_after - renamed_uuids]
    renamed_items = [(items_before[uuid], items_after[uuid]) for uuid in renamed_uuids]
    return added_items, removed_items, renamed_items


def ensure_uuid(blender_collection):
    for item in blender_collection:
        if item.get("dccsync_uuid") is None:
            item.dccsync_uuid = str(uuid4())


class StructDiff:
    def diff(self, proxy_struct: "StructProxy", blender_struct):
        pass


class CollectionDiff:
    items_added: Mapping[str, str] = None
    items_removed: Mapping[str, str] = None
    items_renamed: Mapping[str, str] = None

    def __init__(self):
        pass

    def diff(self, proxy_collection, blender_collection: bpy.types.bpy_prop_collection):
        items_after = {item.dccsync_uuid: name for name, item in blender_collection.items()}
        items_before = {scene.dccsync_uuid: name for name, scene in proxy_collection.items()}
        self.items_added, self.items_removed, self.items_renamed = find_renamed(items_before, items_after)


def diff_data(proxy_data, blender_data):
    attrs = dir(blender_data)
    # Comparable attributes otherwise recurse
    changed_attrs = []
    for attr in attrs:
        if not proxy_data.hasattr(attr) or proxy_data.get(attr) != blender_data.get(attr):
            changed_attrs.append(attr)
