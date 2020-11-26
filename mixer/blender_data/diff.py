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
from typing import List, Dict, Tuple, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.filter import SynchronizedProperties, skip_bpy_data_item
from mixer.blender_data.proxy import ensure_uuid

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import BpyDataProxy
    from mixer.blender_data.datablock_collection_proxy import DatablockCollectionProxy

ItemsRemoved = List[DatablockProxy]
ItemsRenamed = List[Tuple[DatablockProxy, str]]
"""(proxy, old_name)"""

ItemsAdded = List[Tuple[T.ID, str]]
"""datablock : collection_name"""

logger = logging.getLogger(__name__)
Uuid = str
BpyDataCollectionName = str


class BpyDataCollectionDiff:
    """
    Diff between Blender state and proxy state for a bpy.data collection.
    """

    def __init__(self):
        self._items_added: ItemsAdded = {}
        self._items_removed: ItemsRemoved = []
        self._items_renamed: ItemsRenamed = []

    @property
    def items_added(self):
        return self._items_added

    @property
    def items_removed(self):
        return self._items_removed

    @property
    def items_renamed(self):
        return self._items_renamed

    def diff(
        self, proxy: DatablockCollectionProxy, collection_name: str, synchronized_properties: SynchronizedProperties
    ):
        self._items_added.clear()
        self._items_removed.clear()
        self._items_renamed.clear()
        proxies = {datablock_proxy.mixer_uuid: datablock_proxy for datablock_proxy in proxy._data.values()}
        bl_collection = getattr(bpy.data, collection_name)

        # (item name, collection name)
        blender_items: Dict[Uuid, Tuple[T.ID, str]] = {}

        for datablock in bl_collection.values():
            if skip_bpy_data_item(collection_name, datablock):
                continue

            uuid = datablock.mixer_uuid
            if uuid in blender_items.keys():
                # duplicate uuid, from an object duplication
                duplicate_name, duplicate_collection_name = blender_items[uuid]
                logger.info(
                    f"Duplicate uuid {uuid} in bpy.data.{duplicate_collection_name} for {duplicate_name} and bpy.data.{collection_name} for {datablock.name_full}..."
                )
                logger.info("... assuming object was duplicated. Resetting (not an error)")
                # reset the uuid, ensure will regenerate
                datablock.mixer_uuid = ""

            ensure_uuid(datablock)
            if datablock.mixer_uuid in blender_items.keys():
                logger.error(f"Duplicate uuid found for {datablock}")
                continue

            blender_items[datablock.mixer_uuid] = (datablock, collection_name)

        proxy_uuids = set(proxies.keys())
        blender_uuids = set(blender_items.keys())

        # TODO LIB
        renamed_uuids = {
            uuid for uuid in blender_uuids & proxy_uuids if proxies[uuid].data("name") != blender_items[uuid][0].name
        }
        added_uuids = blender_uuids - proxy_uuids - renamed_uuids
        removed_uuids = proxy_uuids - blender_uuids - renamed_uuids

        # this finds standalone datablock, link datablocks and override datablocks
        self._items_added = [(blender_items[uuid][0], blender_items[uuid][1]) for uuid in added_uuids]
        self._items_removed = [proxies[uuid] for uuid in removed_uuids]

        # TODO LIB
        self._items_renamed = [(proxies[uuid], blender_items[uuid][0].name) for uuid in renamed_uuids]

    def empty(self):
        return not (self._items_added or self._items_removed or self._items_renamed)


class BpyBlendDiff:
    """
    Diff for the whole bpy.data
    """

    def __init__(self):
        self._collection_deltas: List[Tuple[BpyDataCollectionName, BpyDataCollectionDiff]] = []
        """A list of deltas per bpy.data collection. Use a list because if will be sorted later"""

    @property
    def collection_deltas(self):
        return self._collection_deltas

    def diff(self, blend_proxy: BpyDataProxy, synchronized_properties: SynchronizedProperties):
        self._collection_deltas.clear()

        for collection_name, _ in synchronized_properties.properties(bpy_type=T.BlendData):
            if collection_name not in blend_proxy._data:
                continue
            delta = BpyDataCollectionDiff()
            delta.diff(blend_proxy._data[collection_name], collection_name, synchronized_properties)
            if not delta.empty():
                self._collection_deltas.append((collection_name, delta))

        # Before this change:
        # Only datablocks handled by the generic synchronization system get a uuid, either from
        # BpyDataProxy.initialize_ref_targets() during room creation, or later during diff processing.
        # Datablocks of unhandled types get no uuid and DatablockRefProxy references to them are incorrect.
        # What is more, this means trouble for tests since datablocks of unhandled types are assigned
        # a uuid during the message grabbing, which means that they get different uuids on both ends.
        for collection_name in synchronized_properties.unhandled_bpy_data_collection_names:
            collection = getattr(bpy.data, collection_name)
            for datablock in collection.values():
                ensure_uuid(datablock)
