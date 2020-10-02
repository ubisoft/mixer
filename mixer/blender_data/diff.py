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
Classes and methods to compute the difference between a BpyDataProxy and the bpy.data collections.

It computes datablock additions, removals and renames.
This module was written before the proxy system implements differential synchronization (Proxy.diff() and Proxy.apply())
and its functionality should move into BpyDataProxy

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import List, Mapping, Tuple, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.filter import Context, skip_bpy_data_item
from mixer.blender_data.proxy import ensure_uuid

if TYPE_CHECKING:
    from mixer.blender_data.proxy import BpyDataProxy
    from mixer.blender_data.datablock_proxy import DatablockProxy
    from mixer.blender_data.datablock_collection_proxy import DatablockCollectionProxy

    ItemsRemoved = List[DatablockProxy]
    ItemsRenamed = List[Tuple[DatablockProxy, str]]

logger = logging.getLogger(__name__)
Uuid = str
BlendDataCollectionName = str
ItemsAdded = Mapping[str, str]
# Item_name : collection_name

# (proxy, old_name)


def find_renamed(
    proxy_items: Mapping[Uuid, DatablockProxy], blender_items: Mapping[Uuid, Tuple[str, str]]
) -> Tuple[ItemsAdded, ItemsRemoved, ItemsRenamed]:
    """
    Split before/after mappings into added/removed/renamed

    Rename detection is based on the mapping keys (e.g. uuids)
    """
    proxy_uuids = set(proxy_items.keys())
    blender_uuids = set(blender_items.keys())

    renamed_uuids = {
        uuid for uuid in blender_uuids & proxy_uuids if proxy_items[uuid].data("name") != blender_items[uuid][0]
    }
    added_uuids = blender_uuids - proxy_uuids - renamed_uuids
    removed_uuids = proxy_uuids - blender_uuids - renamed_uuids

    added_items = {blender_items[uuid][0]: blender_items[uuid][1] for uuid in added_uuids}
    removed_items = [proxy_items[uuid] for uuid in removed_uuids]

    # (proxy, old_name)
    renamed_items = [(proxy_items[uuid], blender_items[uuid][0]) for uuid in renamed_uuids]

    return added_items, removed_items, renamed_items


class BpyDiff:
    pass


class BpyPropCollectionDiff(BpyDiff):
    """
    Diff for a bpy_prop_collection. May not work as is for bpy_prop_collection not in bpy.data
    """

    items_added: ItemsAdded = {}
    items_removed: ItemsRemoved = []
    items_renamed: ItemsRenamed = []

    def diff(self, proxy: DatablockCollectionProxy, collection_name: str, context: Context):
        self.items_added.clear()
        self.items_removed.clear()
        self.items_renamed.clear()
        proxy_items = {id_proxy.mixer_uuid(): id_proxy for id_proxy in proxy._data.values()}
        bl_collection = getattr(bpy.data, collection_name)
        blender_items = {}
        for name, item in bl_collection.items():
            if skip_bpy_data_item(collection_name, item):
                continue

            uuid = item.mixer_uuid
            if uuid in blender_items.keys():
                # duplicate uuid, from an object duplication
                original_item = blender_items[uuid]
                logger.info(f"Duplicate uuid {uuid} for {original_item[1]} and {item.name}...")
                logger.info("... assuming object was duplicated. Resetting (not an error)")
                # reset the uuid, ensure will regenerate
                item.mixer_uuid = ""

            ensure_uuid(item)
            if item.mixer_uuid in blender_items.keys():
                logger.error(f"Duplicate uuid found for {item}")
                continue

            blender_items[item.mixer_uuid] = (name, collection_name)
        self.items_added, self.items_removed, self.items_renamed = find_renamed(proxy_items, blender_items)

    def empty(self):
        return not (self.items_added or self.items_removed or self.items_renamed)


class BpyBlendDiff(BpyDiff):
    """
    Diff for the whole bpy.data
    """

    # A list of deltas per bpy.data collection. Use a list because if will be sorted later
    collection_deltas: List[Tuple[BlendDataCollectionName, BpyPropCollectionDiff]] = []

    # TODO cleanup: not used.
    # Will not be used as the per_DI deltas will be limited to the depsgraph updates
    id_deltas: List[Tuple[DatablockProxy, T.ID]] = []

    def diff(self, blend_proxy: BpyDataProxy, context: Context):
        self.collection_deltas.clear()
        self.id_deltas.clear()

        for collection_name, _ in context.properties(bpy_type=T.BlendData):
            if collection_name not in blend_proxy._data:
                continue
            delta = BpyPropCollectionDiff()
            delta.diff(blend_proxy._data[collection_name], collection_name, context)
            if not delta.empty():
                self.collection_deltas.append((collection_name, delta))

        # Before this change:
        # Only datablocks handled by the generic synchronization system get a uuid, either from
        # BpyDataProxy.initialize_ref_targets() during room creation, or later during diff processing.
        # Datablocks of unhandled types get no uuid and DatablockRefProxy references to them are incorrect.
        # What is more, this means trouble for tests since datablocks of unhandled types are assigned
        # a uuid during the message grabbing, which means that they get different uuids on both ends.
        for collection_name in context.unhandled_bpy_data_collection_names:
            collection = getattr(bpy.data, collection_name)
            for datablock in collection.values():
                ensure_uuid(datablock)
