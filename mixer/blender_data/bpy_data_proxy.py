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

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.blenddata import BlendData, collection_name_to_type
from mixer.blender_data.changeset import Changeset, RenameChangeset
from mixer.blender_data.datablock_collection_proxy import DatablockCollectionProxy
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import Context, safe_depsgraph_updates, safe_context
from mixer.blender_data.proxy import DeltaUpdate, ensure_uuid, Proxy

if TYPE_CHECKING:
    from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy

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


@dataclass
class UnresolvedRef:
    """A datablock reference that could not be resolved when target.init() needed to be called
    because the referenced datablock was not yet received.

    No suitable ordering can easily be provided by the sender for many reasons including Collection.children
    referencing other collections and Scene.sequencer strips that can reference other scenes
    """

    target: T.bpy_prop_collection
    proxy: DatablockRefProxy


# Using a context doubles load time in SS2.82. This remains true for a null context
# Remmoving the "with" lines halves loading time (!!)
class DebugContext:
    """
    Context class only used during BpyDataProxy construction, to keep contextual data during traversal
    of the blender data hierarchy and perform safety checks
    """

    serialized_addresses: Set[bpy.types.ID] = set()  # Already serialized addresses (struct or IDs), for debug
    property_stack: List[Tuple[str, any]] = []  # Stack of properties up to this point in the visit
    property_value: Any
    limit_notified: bool = False

    @contextmanager
    def enter(self, property_name, property_value):
        self.property_stack.append((property_name, property_value))
        yield
        self.property_stack.pop()
        self.serialized_addresses.add(id(property_value))

    def visit_depth(self):
        # Utility for debug
        return len(self.property_stack)

    def property_fullpath(self):
        # Utility for debug
        return ".".join([p[0] for p in self.property_stack])


RootIds = Set[T.ID]
IDProxies = Mapping[str, DatablockProxy]
IDs = Mapping[str, T.ID]
UnresolvedRefs = Dict[str, UnresolvedRef]


@dataclass
class VisitState:
    """
    Gathers proxy system state (mainly known datablocks) and properties to synchronize

    TODO remove obsolete members
    """

    root_ids: RootIds
    """Part ot the proxy system state: list of datablocks in bpy.data"""

    id_proxies: IDProxies
    """Part ot the proxy system state: {uuid: DatablockProxy}"""

    ids: IDs
    """Part ot the proxy system state: {uuid: bpy.types.ID}"""

    unresolved_refs: UnresolvedRefs

    context: Context
    """Controls what properties are synchronized"""

    debug_context: DebugContext = DebugContext()


class BpyDataProxy(Proxy):
    """Proxy to bpy.data collections

    This proxy contains a DatablockCollection proxy per synchronized bpy.data collection
    """

    def __init__(self, *args, **kwargs):

        self.root_ids: RootIds = set()
        """ID elements stored in bpy.data.* collections, computed before recursive visit starts:"""

        self.id_proxies: IDProxies = {}

        self.ids: IDs = {}
        """Only needed to cleanup root_ids and id_proxies on ID removal"""

        self._data: Mapping[str, DatablockCollectionProxy] = {
            name: DatablockCollectionProxy() for name in BlendData.instance().collection_names()
        }

        # Pending unresolved references.
        self._unresolved_refs: UnresolvedRefs = defaultdict(list)

    def clear(self):
        self._data.clear()
        self.root_ids.clear()
        self.id_proxies.clear()
        self.ids.clear()

    def visit_state(self, context: Context = safe_context):
        return VisitState(self.root_ids, self.id_proxies, self.ids, self._unresolved_refs, context)

    def get_non_empty_collections(self):
        return {key: value for key, value in self._data.items() if len(value) > 0}

    def initialize_ref_targets(self, context: Context):
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
        for name, _ in context.properties(bpy_type=T.BlendData):
            if name in collection_name_to_type:
                # TODO use BlendData
                bl_collection = getattr(bpy.data, name)
                for _id_name, item in bl_collection.items():
                    uuid = ensure_uuid(item)
                    self.root_ids.add(item)
                    self.ids[uuid] = item

    def load(self, context: Context):
        """Load the current scene into this proxy

        Only used for test. The initial load is performed by update()
        """
        self.initialize_ref_targets(context)
        visit_state = self.visit_state(context)

        for name, _ in context.properties(bpy_type=T.BlendData):
            collection = getattr(bpy.data, name)
            with visit_state.debug_context.enter(name, collection):
                self._data[name] = DatablockCollectionProxy().load_as_ID(collection, visit_state)
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
        self, diff: BpyBlendDiff, context: Context = safe_context, depsgraph_updates: T.bpy_prop_collection = ()
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
        visit_state = self.visit_state(context)

        # sort the updates deppmost first so that the receiver will create meshes and lights
        # before objects, for instance
        deltas = sorted(diff.collection_deltas, key=_pred_by_creation_order)
        for delta_name, delta in deltas:
            collection_changeset = self._data[delta_name].update(delta, visit_state)
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
            proxy = self.id_proxies.get(datablock.mixer_uuid)
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
            delta = proxy.diff(datablock, None, visit_state)
            if delta:
                logger.info("depsgraph update: update %s", datablock)
                # TODO add an apply mode to diff instead to avoid two traversals ?
                proxy.apply_to_proxy(datablock, delta, visit_state)
                changeset.updates.append(delta)
            else:
                logger.info("depsgraph update: ignore empty delta %s", datablock)

        return changeset

    def create_datablock(
        self, incoming_proxy: DatablockProxy, context: Context = safe_context
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

        visit_state = self.visit_state(context)
        return bpy_data_collection_proxy.create_datablock(incoming_proxy, visit_state)

    def update_datablock(self, update: DeltaUpdate, context: Context = safe_context) -> Optional[T.ID]:
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

        visit_state = self.visit_state(context)
        return bpy_data_collection_proxy.update_datablock(update, visit_state)

    def remove_datablock(self, uuid: str):
        """
        Process a received datablock removal command, removing the datablock and updating the proxy state
        """
        proxy = self.id_proxies.get(uuid)
        if proxy is None:
            logger.error(f"remove_datablock(): no proxy for {uuid} (debug info)")

        bpy_data_collection_proxy = self._data.get(proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(f"remove_datablock: no bpy_data_collection_proxy with name {proxy.collection_name} ")
            return None

        datablock = self.ids[uuid]
        bpy_data_collection_proxy.remove_datablock(proxy, datablock)
        self.root_ids.remove(datablock)
        del self.id_proxies[uuid]
        del self.ids[uuid]

    def rename_datablocks(self, items: List[str, str, str]) -> RenameChangeset:
        """
        Process a received datablock rename command, renaming the datablocks and updating the proxy state.
        """
        rename_changeset_to_send: RenameChangeset = []
        renames = []
        for uuid, old_name, new_name in items:
            proxy = self.id_proxies.get(uuid)
            if proxy is None:
                logger.error(f"rename_datablocks(): no proxy for {uuid} (debug info)")
                return

            bpy_data_collection_proxy = self._data.get(proxy.collection_name)
            if bpy_data_collection_proxy is None:
                logger.warning(f"rename_datablock: no bpy_data_collection_proxy with name {proxy.collection_name} ")
                continue

            datablock = self.ids[uuid]
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

    def debug_check_id_proxies(self):
        """To detect stale entries in proxy state during development"""
        return 0
        # try to find stale entries ASAP: access them all
        dummy = 0
        try:
            dummy = sum(len(id_.name) for id_ in self.root_ids)
        except ReferenceError:
            logger.warning("BpyDataProxy: Stale reference in root_ids")
        try:
            dummy = sum(len(id_.name) for id_ in self.ids.values())
        except ReferenceError:
            logger.warning("BpyDataProxy: Stale reference in root_ids")

        return dummy

    def diff(self, context: Context) -> Optional[BpyDataProxy]:
        """Currently for tests only"""
        diff = self.__class__()
        visit_state = self.visit_state(context)
        for name, proxy in self._data.items():
            collection = getattr(bpy.data, name, None)
            if collection is None:
                logger.warning(f"Unknown, collection bpy.data.{name}")
                continue
            collection_property = bpy.data.bl_rna.properties.get(name)
            delta = proxy.diff(collection, collection_property, visit_state)
            if delta is not None:
                diff._data[name] = diff
        if len(diff._data):
            return diff
        return None
