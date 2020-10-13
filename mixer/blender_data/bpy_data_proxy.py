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
This module provides an implementation for the a proxy to the whole Blender data state, i.e the relevant members
of bpy.data.

See synchronization.md
"""
from __future__ import annotations

import array
from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.blenddata import BlendData, collection_name_to_type
from mixer.blender_data.changeset import Changeset, RenameChangeset
from mixer.blender_data.datablock_collection_proxy import DatablockCollectionProxy
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import SynchronizedProperties, safe_depsgraph_updates, safe_properties
from mixer.blender_data.proxy import DeltaUpdate, ensure_uuid, Proxy, MaxDepthExceeded, UnresolvedRefs, Uuid

logger = logging.getLogger(__name__)

# to sort delta in the bottom up order in rough reference hierarchy
# TODO useless since unresolved references are handled
_creation_order = {
    # anything before objects (meshes, lights, cameras)
    # Mesh must be received before Object because Object creation requires the Mesh, that cannot be updated afterwards
    "objects": 10,
    "collections": 20,
    "scenes": 30,
}


def _pred_by_creation_order(item: Tuple[str, Any]):
    return _creation_order.get(item[0], 0)


class RecursionGuard:
    """
    Limits allowed attribute depth, and guards against recursion caused by unfiltered circular references
    """

    MAX_DEPTH = 30

    def __init__(self):
        self._property_stack: List[str] = []

    def push(self, name: str):
        self._property_stack.append(name)
        if len(self._property_stack) > self.MAX_DEPTH:
            property_path = ".".join([p for p in self._property_stack])
            raise MaxDepthExceeded(property_path)

    def pop(self):
        self._property_stack.pop()


@dataclass
class ProxyState:
    """
    State of a BpyDataProxy
    """

    proxies: Dict[Uuid, DatablockProxy] = field(default_factory=dict)
    """known proxies"""

    datablocks: Dict[Uuid, T.ID] = field(default_factory=dict)
    """Known datablocks"""

    unresolved_refs: UnresolvedRefs = UnresolvedRefs()


@dataclass
class VisitState:
    """
    Gathers proxy system state (mainly known datablocks) and properties to synchronize
    """

    Path = List[Union[str, int]]

    datablock_proxy: Optional[DatablockProxy] = None
    """The datablock proxy being visited"""

    path: Path = field(default_factory=list)
    """The path to the current property from the datablock, for instance in GreasePencil
    ["layers", "fills", "frames", 0, "strokes", 1, "points", 0]"""

    recursion_guard: RecursionGuard = RecursionGuard()

    funcs: Dict[str, Callable] = field(default_factory=dict)
    """Functions transmitted from a property to another
    (e.g Mesh transmits clear_geometry that is called if necessary
    by the MeshVertices SoaProxy ) """


@dataclass
class Context:
    proxy_state: ProxyState
    """Proxy system state"""

    synchronized_properties: SynchronizedProperties
    """Controls what properties are synchronized"""

    visit_state: VisitState = VisitState()
    """Current datablock operation state"""


class BpyDataProxy(Proxy):
    """Proxy to bpy.data collections

    This proxy contains a DatablockCollection proxy per synchronized bpy.data collection
    """

    def __init__(self, *args, **kwargs):

        self.state: ProxyState = ProxyState()

        self._data: Dict[str, DatablockCollectionProxy] = {
            name: DatablockCollectionProxy() for name in BlendData.instance().collection_names()
        }

    def clear(self):
        self._data.clear()
        self.state.proxies.clear()
        self.state.datablocks.clear()

    def context(self, synchronized_properties: SynchronizedProperties = safe_properties) -> Context:
        return Context(self.state, synchronized_properties)

    def get_non_empty_collections(self):
        return {key: value for key, value in self._data.items() if len(value) > 0}

    def initialize_ref_targets(self, synchronized_properties: SynchronizedProperties):
        """Keep track of all bpy.data items so that loading recognizes references to them

        Call this before updating the proxy from send_scene_content. It is not needed on the
        receiver side.

        TODO check is this is actually required or if we can rely upon is_embedded_data being False
        """
        # Normal operation no more involve BpyDataProxy.load() ad initial synchronization behaves
        # like a creation. The current load_as_what() implementation relies on root_ids to determine if
        # a T.ID must ne loaded as an IDRef (pointer to bpy.data) or an IDDef (pointer to an "owned" ID).
        # so we need to load all the root_ids before loading anything into the proxy.
        # However, root_ids may no more be required if we can load all the proxies inside out (deepmost first, i.e
        # (Mesh, Metaball, ..), then Object, the Scene). This should be possible as as we sort
        # the updates inside out in update() to the receiver gets them in order
        for name, _ in synchronized_properties.properties(bpy_type=T.BlendData):
            if name in collection_name_to_type:
                # TODO use BlendData
                bl_collection = getattr(bpy.data, name)
                for _id_name, item in bl_collection.items():
                    uuid = ensure_uuid(item)
                    self.state.datablocks[uuid] = item

    def load(self, synchronized_properties: SynchronizedProperties):
        """Load the current scene into this proxy

        Only used for test. The initial load is performed by update()
        """
        self.initialize_ref_targets(synchronized_properties)
        context = self.context(synchronized_properties)

        for name, _ in synchronized_properties.properties(bpy_type=T.BlendData):
            collection = getattr(bpy.data, name)
            self._data[name] = DatablockCollectionProxy().load(collection, context)
        return self

    def find(self, collection_name: str, key: str) -> DatablockProxy:
        # TODO not used ?
        if not self._data:
            return None
        collection_proxy = self._data.get(collection_name)
        if collection_proxy is None:
            return None
        return collection_proxy.find(key)

    def update(
        self,
        diff: BpyBlendDiff,
        synchronized_properties: SynchronizedProperties = safe_properties,
        depsgraph_updates: T.bpy_prop_collection = (),
    ) -> Changeset:
        """
        Process local changes, i.e. created, removed and renames datablocks as well as depsgraph updates.

        This updates the local proxy state and return a Changeset to send to the server. This method is also
        used to send the initial scene contents, which is seen as datablock creations.
        """
        changeset: Changeset = Changeset()

        # Update the bpy.data collections status and get the list of newly created bpy.data entries.
        # Updated proxies will contain the IDs to send as an initial transfer.
        # There is no difference between a creation and a subsequent update
        context = self.context(synchronized_properties)

        # sort the updates deppmost first so that the receiver will create meshes and lights
        # before objects, for instance
        deltas = sorted(diff.collection_deltas, key=_pred_by_creation_order)
        for delta_name, delta in deltas:
            collection_changeset = self._data[delta_name].update(delta, context)
            changeset.creations.extend(collection_changeset.creations)
            changeset.removals.extend(collection_changeset.removals)
            changeset.renames.extend(collection_changeset.renames)

        # Update the ID proxies from the depsgraph update
        # this should iterate inside_out (Object.data, Object) in the adequate creation order
        # (creating an Object requires its data)

        # WARNING:
        #   depsgraph_updates[i].id.original IS NOT bpy.lights['Point']
        # or whatever as you might expect, so you cannot use it to index into the map
        # to find the proxy to update.
        # However
        #   - mixer_uuid attributes have the same value
        #   - __hash__() returns the same value

        depsgraph_updated_ids = reversed([update.id.original for update in depsgraph_updates])
        for datablock in depsgraph_updated_ids:
            if not isinstance(datablock, safe_depsgraph_updates):
                logger.info("depsgraph update: ignoring untracked type %s", datablock)
                continue
            if isinstance(datablock, T.Scene) and datablock.name == "_mixer_to_be_removed_":
                continue
            proxy = self.state.proxies.get(datablock.mixer_uuid)
            if proxy is None:
                # Not an error for embedded IDs.
                if not datablock.is_embedded_data:
                    logger.warning(f"depsgraph update for {datablock} : no proxy and not datablock.is_embedded_data")

                # For instance Scene.node_tree is not a reference to a bpy.data collection element
                # but a "pointer" to a NodeTree owned by Scene. In such a case, the update list contains
                # scene.node_tree, then scene. We can ignore the scene.node_tree update since the
                # processing of scene will process scene.node_tree.
                # However, it is not obvious to detect the safe cases and remove the message in such cases
                logger.info("depsgraph update: Ignoring embedded %s", datablock)
                continue
            delta = proxy.diff(datablock, datablock.name, None, context)
            if delta:
                logger.info("depsgraph update: update %s", datablock)
                # TODO add an apply mode to diff instead to avoid two traversals ?
                proxy.apply_to_proxy(datablock, delta, context)
                changeset.updates.append(delta)
            else:
                logger.info("depsgraph update: ignore empty delta %s", datablock)

        return changeset

    def create_datablock(
        self, incoming_proxy: DatablockProxy, synchronized_properties: SynchronizedProperties = safe_properties
    ) -> Tuple[Optional[T.ID], Optional[RenameChangeset]]:
        """
        Process a received datablock creation command, creating the datablock and updating the proxy state
        """
        bpy_data_collection_proxy = self._data.get(incoming_proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(
                f"create_datablock: no bpy_data_collection_proxy with name {incoming_proxy.collection_name} "
            )
            return None

        context = self.context(synchronized_properties)
        return bpy_data_collection_proxy.create_datablock(incoming_proxy, context)

    def update_datablock(
        self, update: DeltaUpdate, synchronized_properties: SynchronizedProperties = safe_properties
    ) -> Optional[T.ID]:
        """
        Process a received datablock update command, updating the datablock and the proxy state
        """
        assert isinstance(update, DeltaUpdate)
        incoming_proxy: DatablockProxy = update.value
        bpy_data_collection_proxy = self._data.get(incoming_proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(
                f"update_datablock: no bpy_data_collection_proxy with name {incoming_proxy.collection_name} "
            )
            return None

        context = self.context(synchronized_properties)
        return bpy_data_collection_proxy.update_datablock(update, context)

    def remove_datablock(self, uuid: str):
        """
        Process a received datablock removal command, removing the datablock and updating the proxy state
        """
        proxy = self.state.proxies.get(uuid)
        if proxy is None:
            logger.error(f"remove_datablock(): no proxy for {uuid} (debug info)")

        bpy_data_collection_proxy = self._data.get(proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(f"remove_datablock: no bpy_data_collection_proxy with name {proxy.collection_name} ")
            return None

        datablock = self.state.datablocks[uuid]
        bpy_data_collection_proxy.remove_datablock(proxy, datablock)
        del self.state.proxies[uuid]
        del self.state.datablocks[uuid]

    def rename_datablocks(self, items: List[str, str, str]) -> RenameChangeset:
        """
        Process a received datablock rename command, renaming the datablocks and updating the proxy state.
        """
        rename_changeset_to_send: RenameChangeset = []
        renames = []
        for uuid, old_name, new_name in items:
            proxy = self.state.proxies.get(uuid)
            if proxy is None:
                logger.error(f"rename_datablocks(): no proxy for {uuid} (debug info)")
                return

            bpy_data_collection_proxy = self._data.get(proxy.collection_name)
            if bpy_data_collection_proxy is None:
                logger.warning(f"rename_datablock: no bpy_data_collection_proxy with name {proxy.collection_name} ")
                continue

            datablock = self.state.datablocks[uuid]
            tmp_name = f"_mixer_tmp_{uuid}"
            if datablock.name != new_name and datablock.name != old_name:
                # local receives a rename, but its datablock name does not match the remote datablock name before
                # the rename. This means that one of these happened:
                # - local has renamed the datablock and remote will receive the rename command later on
                # - local has processed a rename command that remote had not yet processed, but will process later on
                # ensure that everyone renames its datablock with the **same** name
                new_name = new_name = f"_mixer_rename_conflict_{uuid}"
                logger.warning(f"rename_datablocks: conflict for existing {datablock}")
                logger.warning(f'... incoming old name "{old_name}" new name "{new_name}"')
                logger.warning(f"... using {new_name}")

                # Strangely, for collections not everyone always detect a conflict, so rename for everyone
                rename_changeset_to_send.append(
                    (
                        datablock.mixer_uuid,
                        datablock.name,
                        new_name,
                        f"Conflict bpy.data.{proxy.collection_name}[{datablock.name}] into {new_name}",
                    )
                )

            renames.append([bpy_data_collection_proxy, proxy, old_name, tmp_name, new_name, datablock])

        # The rename process is handled in two phases to avoid spontaneous renames from Blender
        # see DatablockCollectionProxy.update() for explanation
        for bpy_data_collection_proxy, proxy, _, tmp_name, _, datablock in renames:
            bpy_data_collection_proxy.rename_datablock(proxy, tmp_name, datablock)

        for bpy_data_collection_proxy, proxy, _, _, new_name, datablock in renames:
            bpy_data_collection_proxy.rename_datablock(proxy, new_name, datablock)

        return rename_changeset_to_send

    def diff(self, synchronized_properties: SynchronizedProperties) -> Optional[BpyDataProxy]:
        """Currently for tests only"""
        diff = self.__class__()
        context = self.context(synchronized_properties)
        for name, proxy in self._data.items():
            collection = getattr(bpy.data, name, None)
            if collection is None:
                logger.warning(f"Unknown, collection bpy.data.{name}")
                continue
            collection_property = bpy.data.bl_rna.properties.get(name)
            delta = proxy.diff(collection, collection_property, context)
            if delta is not None:
                diff._data[name] = diff
        if len(diff._data):
            return diff
        return None

    def update_soa(self, uuid: Uuid, path: List[Union[int, str]], soas: List[Tuple[str, array.array]]):
        datablock_proxy = self.state.proxies[uuid]
        datablock = self.state.datablocks[uuid]
        datablock_proxy.update_soa(datablock, path, soas)
