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

from __future__ import annotations

import logging
import traceback
from typing import Any, Mapping, Optional, Tuple, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.attributes import diff_attribute, read_attribute, write_attribute
from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy
from mixer.blender_data.diff import BpyPropCollectionDiff
from mixer.blender_data.filter import skip_bpy_data_item
from mixer.blender_data.proxy import DeltaUpdate, DeltaAddition, DeltaDeletion
from mixer.blender_data.proxy import ensure_uuid, Proxy
from mixer.blender_data.changeset import Changeset, RenameChangeset

if TYPE_CHECKING:
    from mixer.blender_data.proxy import VisitState


logger = logging.getLogger(__name__)


class DatablockCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of standalone datablocks, be it one of bpy.data collections
    or a collection like Scene.collection.objects.

    This proxy keeps track of the state of the whole collection. If the tracked collection is a bpy.data
    collection (e.g.bpy.data.objects), the proxy contents will be instances of DatablockProxy.
    Otherwise (e.g. Scene.collection.objects) the proxy contents are instances of DatablockRefProxy
    that reference items in bpy.data collections
    """

    def __init__(self):
        # On item per datablock. The key is the uuid, which eases rename management
        self._data: Mapping[str, DatablockProxy] = {}

    def __len__(self):
        return len(self._data)

    def load_as_ID(self, bl_collection: bpy.types.bpy_prop_collection, visit_state: VisitState):  # noqa N802
        """
        Load bl_collection elements as plain IDs, with all element properties. Use this to load from bpy.data
        """
        for name, item in bl_collection.items():
            collection_name = BlendData.instance().bl_collection_name_from_ID(item)
            if skip_bpy_data_item(collection_name, item):
                continue
            with visit_state.debug_context.enter(name, item):
                uuid = ensure_uuid(item)
                # # HACK: Skip objects with a mesh in order to process D.objects withtout processing D.meshes
                # # - writing meshes is not currently implemented and we must avoid double processing with VRtist
                # # - reading objects is required for metaballs
                # if collection_name == "objects" and isinstance(item.data, T.Mesh):
                #     continue
                # # /HACK
                self._data[uuid] = DatablockProxy().load(item, visit_state, bpy_data_collection_name=collection_name)

        return self

    def load_as_IDref(self, bl_collection: bpy.types.bpy_prop_collection, visit_state: VisitState):  # noqa N802
        """
        Load bl_collection elements as referenced into bpy.data
        """
        for name, item in bl_collection.items():
            with visit_state.debug_context.enter(name, item):
                uuid = item.mixer_uuid
                self._data[uuid] = DatablockRefProxy().load(item, visit_state)
        return self

    def save(self, parent: Any, key: str, visit_state: VisitState):
        """
        Save this Proxy into a Blender property
        """
        if not self._data:
            return

        target = getattr(parent, key, None)
        if target is None:
            # Don't log this, too many messages
            # f"Saving {self} into non existent attribute {bl_instance}.{attr_name} : ignored"
            return

        link = getattr(target, "link", None)
        unlink = getattr(target, "unlink", None)
        if link is not None and unlink is not None:
            if not len(target):
                for _, ref_proxy in self._data.items():
                    datablock = ref_proxy.target(visit_state)
                    if datablock:
                        link(datablock)
                    else:
                        # The reference will be resolved when the referenced datablock will be loaded
                        uuid = ref_proxy._datablock_uuid
                        logger.info(f"unresolved reference {parent}.{key} -> {ref_proxy}")
                        unresolved_list = visit_state.unresolved_refs[uuid]
                        unresolved_list.append((target, ref_proxy))
            else:
                logger.warning(f"Saving into non empty collection: {target}. Ignored")
        else:
            for k, v in self._data.items():
                write_attribute(target, k, v, visit_state)

    def find(self, key: str):
        return self._data.get(key)

    def create_datablock(
        self, incoming_proxy: DatablockProxy, visit_state: VisitState
    ) -> Tuple[Optional[T.ID], Optional[RenameChangeset]]:
        """Create a bpy.data datablock from a received DatablockProxy and update the proxy structures accordingly

        Receiver side

        Args:
            incoming_proxy : this proxy contents is used to update the bpy.data collection item
        """

        datablock, renames = incoming_proxy.create_standalone_datablock(visit_state)

        # One existing scene from the document loaded at join time could not be removed. Remove it now
        if (
            incoming_proxy.collection_name == "scenes"
            and len(bpy.data.scenes) == 2
            and bpy.data.scenes[0].name == "_mixer_to_be_removed_"
        ):
            from mixer.blender_client.scene import delete_scene

            delete_scene(bpy.data.scenes[0])

        if not datablock:
            return None, None

        uuid = incoming_proxy.mixer_uuid()
        self._data[uuid] = incoming_proxy
        visit_state.root_ids.add(datablock)
        visit_state.ids[uuid] = datablock
        visit_state.id_proxies[uuid] = incoming_proxy

        unresolved_refs = visit_state.unresolved_refs.get(uuid)
        if unresolved_refs:
            for collection, ref_proxy in unresolved_refs:
                ref_target = ref_proxy.target(visit_state)
                logger.info(f"create_datablock: resolving reference {collection}.link({ref_target}")
                collection.link(ref_target)
            del visit_state.unresolved_refs[uuid]

        return datablock, renames

    def update_datablock(self, delta: DeltaUpdate, visit_state: VisitState):
        """Update a bpy.data item from a received DatablockProxy and update the proxy structures accordingly

        Receiver side

        Args:
            proxy : this proxy contents is used to update the bpy.data collection item
        """
        incoming_proxy = delta.value
        uuid = incoming_proxy.mixer_uuid()

        proxy: DatablockProxy = visit_state.id_proxies.get(uuid)
        if proxy is None:
            logger.error(
                f"update_datablock(): Missing proxy for bpy.data.{incoming_proxy.collection_name}[{incoming_proxy.data('name')}] uuid {uuid}"
            )
            return

        if proxy.mixer_uuid() != incoming_proxy.mixer_uuid():
            logger.error(
                f"update_datablock : uuid mismatch between incoming {incoming_proxy.mixer_uuid()} ({incoming_proxy}) and existing {proxy.mixer_uuid} ({proxy})"
            )
            return

        # the ID will have changed if the object has been morphed (change light type, for instance)
        existing_id = visit_state.ids.get(uuid)
        if existing_id is None:
            logger.warning(f"Non existent uuid {uuid} while updating {proxy.collection_name}[{proxy.data('name')}]")
            return None

        id_ = proxy.update_standalone_datablock(existing_id, delta, visit_state)
        if existing_id != id_:
            # Not a problem for light morphing
            logger.warning(f"Update_datablock changes datablock {existing_id} to {id_}")
            visit_state.root_ids.remove(existing_id)
            visit_state.root_ids.add(id_)
            visit_state.ids[uuid] = id_

        return id_

    def remove_datablock(self, proxy: DatablockProxy, datablock: T.ID):
        """Remove a bpy.data collection item and update the proxy structures

        Receiver side

        Args:
            uuid: the mixer_uuid of the datablock
        """
        # TODO scene and last_scene_ ...
        logger.info("Perform removal for %s", proxy)
        try:
            if isinstance(datablock, T.Scene):
                from mixer.blender_client.scene import delete_scene

                delete_scene(datablock)
            else:
                proxy.collection.remove(datablock)
        except ReferenceError as e:
            # We probably have processed previously the deletion of a datablock referenced by Object.data (e.g. Light).
            # On both sides it deletes the Object as well. So the sender issues a message for object deletion
            # but deleting the light on this side has already deleted the object.
            # Alternatively we could try to sort messages on the sender side
            logger.warning(f"Exception during remove_datablock for {proxy}")
            logger.warning(f"... {e}")
        uuid = proxy.mixer_uuid()
        del self._data[uuid]

    def rename_datablock(self, proxy: DatablockProxy, new_name: str, datablock: T.ID):
        """
        Rename a bpy.data collection item and update the proxy structures

        Receiver side

        Args:
            uuid: the mixer_uuid of the datablock
        """
        logger.info("rename_datablock proxy %s datablock %s into %s", proxy, datablock, new_name)
        proxy.rename(new_name)
        datablock.name = new_name

    def update(self, diff: BpyPropCollectionDiff, visit_state: VisitState) -> Changeset:
        """
        Update the proxy according to the diff
        """
        changeset = Changeset()
        # Sort so that the tests receive the messages in deterministic order. Sad but not very harmfull
        added_names = sorted(diff.items_added.keys())
        for name in added_names:
            collection_name = diff.items_added[name]
            logger.info("Perform update/creation for %s[%s]", collection_name, name)
            try:
                # TODO could have a datablock directly
                collection = getattr(bpy.data, collection_name)
                id_ = collection.get(name)
                if id_ is None:
                    logger.error("update/ request addition for %s[%s] : not found", collection_name, name)
                    continue
                uuid = ensure_uuid(id_)
                visit_state.root_ids.add(id_)
                visit_state.ids[uuid] = id_
                proxy = DatablockProxy().load(id_, visit_state, bpy_data_collection_name=collection_name)
                visit_state.id_proxies[uuid] = proxy
                self._data[uuid] = proxy
                changeset.creations.append(proxy)
            except Exception:
                logger.error(f"Exception during update/added for {collection_name}[{name}]:")
                for line in traceback.format_exc().splitlines():
                    logger.error(line)

        for proxy in diff.items_removed:
            try:
                logger.info("Perform removal for %s", proxy)
                uuid = proxy.mixer_uuid()
                changeset.removals.append((uuid, str(proxy)))
                del self._data[uuid]
                id_ = visit_state.ids[uuid]
                visit_state.root_ids.remove(id_)
                del visit_state.id_proxies[uuid]
                del visit_state.ids[uuid]
            except Exception:
                logger.error(f"Exception during update/removed for proxy {proxy})  :")
                for line in traceback.format_exc().splitlines():
                    logger.error(line)

        #
        # Handle spontaneous renames
        #
        # Say
        # - local and remote are synced with 2 objects with uuid/name D7/A FC/B
        # - local renames D7/A into B
        #   - D7 is actually renamed into B.001 !
        #   - we detect (D7 -> B.001)
        #   - remote proceses normally
        # - local renames D7/B.001 into B
        #   - D7 is renamed into B
        #   - FC is renamed into B.001
        #   - we detect (D7->B, FC->B.001)
        #   - local result is (D7/B, FC/B.001)
        # - local repeatedly renames the item named B.001 into B
        # - at some point on remote, the execution of a rename command will provoke a spontaneous rename,
        #   resulting in a situation where remote has FC/B.001 and D7/B.002 linked to the
        #   Master collection and also a FC/B unlinked
        #
        for proxy, new_name in diff.items_renamed:
            uuid = proxy.mixer_uuid()
            if proxy.collection[new_name] is not visit_state.ids[uuid]:
                logger.error(
                    f"update rename : {proxy.collection}[{new_name}] is not {visit_state.ids[uuid]} for {proxy}, {uuid}"
                )
            if visit_state.ids[uuid] not in visit_state.root_ids:
                logger.error(f"update rename : {visit_state.ids[uuid]} not in visit_state.root_ids for {proxy}, {uuid}")

            old_name = proxy.data("name")
            changeset.renames.append((proxy.mixer_uuid(), old_name, new_name, str(proxy)))
            proxy.rename(new_name)

        return changeset

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        collection_delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> DatablockCollectionProxy:

        # WARNING this is only for collections of IDrefs, like Scene.collection.objects
        # not the right place

        collection_update: DatablockCollectionProxy = collection_delta.value
        assert type(collection_update) == type(self)
        collection = getattr(parent, key)
        for k, ref_delta in collection_update._data.items():
            try:
                if not isinstance(ref_delta, (DeltaAddition, DeltaDeletion)):
                    logger.warning(f"unexpected type for delta at {collection}[{k}]: {ref_delta}. Ignored")
                    continue
                ref_update: DatablockRefProxy = ref_delta.value
                if not isinstance(ref_update, DatablockRefProxy):
                    logger.warning(f"unexpected type for delta_value at {collection}[{k}]: {ref_update}. Ignored")
                    continue

                assert isinstance(ref_update, DatablockRefProxy)
                if to_blender:
                    # TODO another case for rename trouble ik k remains the name
                    # should be fixed automatically if the key is the uuid at
                    # DatablockCollectionProxy load
                    uuid = ref_update._datablock_uuid
                    datablock = visit_state.ids.get(uuid)
                    if datablock is None:
                        logger.warning(
                            f"delta apply for {parent}[{key}]: unregistered uuid {uuid} for {ref_update._debug_name}"
                        )
                        continue
                    if isinstance(ref_delta, DeltaAddition):
                        collection.link(datablock)
                    else:
                        collection.unlink(datablock)

                if isinstance(ref_delta, DeltaAddition):
                    self._data[k] = ref_update
                else:
                    del self._data[k]
            except Exception as e:
                logger.warning(f"DatablockCollectionProxy.apply(). Processing {ref_delta} to_blender {to_blender}")
                logger.warning(f"... for {collection}[{k}]")
                logger.warning(f"... Exception: {e}")
                logger.warning("... Update ignored")
                continue

        return self

    def diff(
        self, collection: T.bpy_prop_collection, collection_property: T.Property, visit_state: VisitState
    ) -> Optional[DeltaUpdate]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        As this proxy tracks a collection, the result will be a DeltaUpdate that contains a DatablockCollectionProxy
        with an Delta item per added, deleted or update item

        Args:
            collection: the collection diff against this proxy
            collection_property: the property of collection in its enclosing object
        """

        # This method is called from the depsgraph handler. The proxy holds a representation of the Blender state
        # before the modification being processed. So the changeset is (Blender state - proxy state)

        # TODO how can this replace BpyBlendDiff ?

        diff = self.__class__()

        item_property = collection_property.fixed_type

        # keys are uuids
        proxy_keys = self._data.keys()
        blender_items = {item.mixer_uuid: item for item in collection.values()}
        blender_keys = blender_items.keys()
        added_keys = blender_keys - proxy_keys
        deleted_keys = proxy_keys - blender_keys
        maybe_updated_keys = proxy_keys & blender_keys

        for k in added_keys:
            value = read_attribute(blender_items[k], item_property, visit_state)
            assert isinstance(value, (DatablockProxy, DatablockRefProxy))
            diff._data[k] = DeltaAddition(value)

        for k in deleted_keys:
            diff._data[k] = DeltaDeletion(self._data[k])

        for k in maybe_updated_keys:
            delta = diff_attribute(blender_items[k], item_property, self.data(k), visit_state)
            if delta is not None:
                assert isinstance(delta, DeltaUpdate)
                diff._data[k] = delta

        if len(diff._data):
            return DeltaUpdate(diff)

        return None

    def search(self, name: str) -> [DatablockProxy]:
        """Convenience method to find proxies by name instead of uuid (for tests only)"""
        results = []
        for uuid in self._data.keys():
            proxy_or_update = self.data(uuid)
            proxy = proxy_or_update if isinstance(proxy_or_update, Proxy) else proxy_or_update.value
            if proxy.data("name") == name:
                results.append(proxy)
        return results

    def search_one(self, name: str) -> DatablockProxy:
        """Convenience method to find a proxy by name instead of uuid (for tests only)"""
        results = self.search(name)
        return None if not results else results[0]
