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
Proxy of a datablock

See synchronization.md
"""
from __future__ import annotations

from collections import defaultdict
import logging
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING, Union
import pathlib

import bpy
import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.blenddata import rna_identifier_to_collection_name

from mixer.blender_data.attributes import read_attribute, write_attribute
from mixer.blender_data.proxy import Delta, DeltaReplace, DeltaUpdate
from mixer.blender_data.misc_proxies import CustomPropertiesProxy
from mixer.blender_data.struct_proxy import StructProxy
from mixer.blender_data.type_helpers import sub_id_type
from mixer.local_data import get_source_file_path
from mixer.bl_utils import get_mixer_prefs

if TYPE_CHECKING:
    from mixer.blender_data.aos_soa_proxy import SoaElement
    from mixer.blender_data.bpy_data_proxy import RenameChangeset, Context, VisitState
    from mixer.blender_data.types import ArrayGroups, Path, SoaMember


DEBUG = True

logger = logging.getLogger(__name__)


class DatablockProxy(StructProxy):
    """
    Proxy to a datablock, standalone (bpy.data.cameras['Camera']) or embedded.
    """

    _serialize = (
        "_bpy_data_collection",
        "_class_name",
        "_datablock_uuid",
        "_custom_properties",
        "_is_in_workspace",
        "_filepath_raw",
    )

    def __init__(self):
        super().__init__()

        self._bpy_data_collection: str = ""
        """name of the bpy.data collection this datablock belongs to, None if embedded in another datablock"""

        self._class_name: str = ""
        self._datablock_uuid: str = ""

        self._soas: Dict[VisitState.Path, List[Tuple[str, SoaElement]]] = defaultdict(list)
        """e.g. {
            ("vertices"): [("co", co_soa), ("normals", normals_soa)]
            ("edges"): ...
        }"""

        # TODO move into _arrays
        self._media: Optional[Tuple[str, bytes]] = None
        self._is_in_workspace: Optional[bool] = None
        self._filepath_raw: Optional[str] = None

        self._arrays: ArrayGroups = {}
        """arrays that must not be serialized as json because of their size"""

        self._initialized = False

        self._custom_properties = CustomPropertiesProxy()

    def copy_data(self, other: DatablockProxy):
        super().copy_data(other)
        self._soas = other._soas
        self._media = other._media
        self._arrays = other._arrays

    def clear_data(self):
        super().clear_data()
        self._soas.clear()
        self._arrays.clear()
        if self._media:
            self._media.clear()

    def init(self, datablock: T.ID):
        if datablock is not None:
            if not datablock.is_embedded_data:
                type_name = sub_id_type(type(datablock)).bl_rna.identifier
                self._bpy_data_collection = rna_identifier_to_collection_name[type_name]
                self._datablock_uuid = datablock.mixer_uuid
            self._class_name = datablock.__class__.__name__
            self._initialized = True

    @property
    def arrays(self):
        return self._arrays

    @arrays.setter
    def arrays(self, arrays: ArrayGroups):
        self._arrays = arrays

    @classmethod
    def make(cls, datablock: T.ID):

        if isinstance(datablock, T.Object):
            from mixer.blender_data.object_proxy import ObjectProxy

            return ObjectProxy()
        if isinstance(datablock, T.Mesh):
            from mixer.blender_data.mesh_proxy import MeshProxy

            return MeshProxy()

        if isinstance(datablock, T.Key):
            from mixer.blender_data.shape_key_proxy import ShapeKeyProxy

            return ShapeKeyProxy()
        return DatablockProxy()

    @property
    def is_standalone_datablock(self):
        return bool(self._bpy_data_collection)

    @property
    def is_embedded_data(self):
        return not self.is_standalone_datablock

    @property
    def mixer_uuid(self) -> str:
        return self._datablock_uuid

    def rename(self, new_name: str):
        self._data["name"] = new_name

    def __str__(self) -> str:
        return f"DatablockProxy {self.mixer_uuid} for bpy.data.{self.collection_name}[{self.data('name')}]"

    def load(
        self,
        datablock: T.ID,
        context: Context,
        bpy_data_collection_name: str = None,
    ) -> DatablockProxy:
        """Load a datablock into this proxy

        Args:
            datablock: the datablock to load into this proxy, may be standalone or embedded
            context: visit and proxy state
            bpy_data_collection_name: if datablock is standalone, name of the bpy.data collection that owns datablock,
            otherwise None

        Returns:
            this DatablockProxy
        """

        if not self._initialized:
            if bpy_data_collection_name is None:
                # TODO would be better to load embedded datablocks into StructProxy and use DatablockProxy
                # only for standalone datablocks
                assert datablock.is_embedded_data, f"load: {datablock} is not embedded and collection_name is None"
                self._bpy_data_collection = ""
            else:
                assert (
                    not datablock.is_embedded_data
                ), f"load: {datablock} is embedded and collection_name is {bpy_data_collection_name}"
                self._bpy_data_collection = bpy_data_collection_name
            self._initialized = True

        self._class_name = datablock.__class__.__name__
        self.clear_data()
        properties = context.synchronized_properties.properties(datablock)
        # this assumes that specifics.py apply only to ID, not Struct
        properties = specifics.conditional_properties(datablock, properties)
        try:
            context.visit_state.datablock_proxy = self
            for name, bl_rna_property in properties:
                attr = getattr(datablock, name)
                attr_value = read_attribute(attr, name, bl_rna_property, context)
                # Also write None values to reset attributes like Camera.dof.focus_object
                # TODO for scene, test difference, only send update if dirty as continuous updates to scene
                # master collection will conflicting writes with Master Collection
                self._data[name] = attr_value
        finally:
            context.visit_state.datablock_proxy = None

        specifics.post_save_id(self, datablock)

        uuid = datablock.get("mixer_uuid")
        if uuid:
            # It is a bpy.data ID, not an ID "embedded" inside another ID, like scene.collection
            id_ = context.proxy_state.datablocks.get(uuid)
            if id_ is not datablock:
                # this occurs when
                # - when we find a reference to a BlendData ID that was not loaded
                # - the ID are not properly ordred at creation time, for instance (objects, meshes)
                # instead of (meshes, objects) : a bug
                logger.debug("DatablockProxy.load(): %s not in context.proxy_state.datablocks[uuid]", datablock)
            self._datablock_uuid = datablock.mixer_uuid
            context.proxy_state.proxies[uuid] = self

        self.attach_filepath_raw(datablock)
        self.attach_media_descriptor(datablock)
        self._custom_properties.load(datablock)
        return self

    def attach_filepath_raw(self, datablock: T.ID):
        if isinstance(datablock, T.Image):
            path = get_source_file_path(bpy.path.abspath(datablock.filepath))
            self._filepath_raw = str(pathlib.Path(path).resolve(strict=False))

    def is_file_in_workspace(self, filepath):
        filepath = str(pathlib.Path(filepath))
        for item in get_mixer_prefs().workspace_directories:
            workspace = item.workspace
            if filepath.startswith(str(pathlib.Path(workspace))):
                return True
        return False

    def attach_media_descriptor(self, datablock: T.ID):
        # if Image, Sound, Library, MovieClip, Text, VectorFont, Volume
        # create a self._media with the data to be sent
        # - filepath
        # - reference to the packed data if packed
        #
        #
        if isinstance(datablock, T.Image):
            self._is_in_workspace = False
            packed_file = datablock.packed_file
            data = None
            if packed_file is not None:
                data = packed_file.data
                self._media = (get_source_file_path(self._filepath_raw), data)
                return

            if self.is_file_in_workspace(self._filepath_raw):
                self._is_in_workspace = True
                self._media = None
                return

            path = get_source_file_path(self._filepath_raw)
            with open(bpy.path.abspath(path), "rb") as data_file:
                data = data_file.read()
            self._media = (path, data)

    @property
    def collection_name(self) -> str:
        """
        The name of the bpy.data collection that contains the proxified datablock, empty string if the
        proxified datablock is embedded
        """
        return self._bpy_data_collection

    @property
    def collection(self) -> T.bpy_prop_collection:
        return getattr(bpy.data, self.collection_name)

    def target(self, context: Context) -> T.ID:
        """Returns the datablock proxified by this proxy"""
        return context.proxy_state.datablocks.get(self.mixer_uuid)

    def create_standalone_datablock(self, context: Context) -> Tuple[Optional[T.ID], Optional[RenameChangeset]]:
        """
        Save this proxy into its target standalone datablock
        """
        if self.target(context):
            logger.warning(f"create_standalone_datablock: datablock already registered : {self}")
            logger.warning("... update ignored")
            return None, None
        renames: RenameChangeset = []
        incoming_name = self.data("name")

        # Detect a conflicting creation
        existing_datablock = self.collection.get(incoming_name)
        if existing_datablock:
            if not existing_datablock.mixer_uuid:
                # A datablock created by VRtist command in the same command batch
                # Not an error, we will make it ours by adding the uuid and registering it

                # TODO this branch should be obsolete as VRtist commands are no more processed in generic mode
                logger.info(f"create_standalone_datablock for {self} found existing datablock from VRtist")
                datablock = existing_datablock
            else:
                if existing_datablock.mixer_uuid != self.mixer_uuid:
                    # TODO LIB

                    # local has a datablock with the same name as remote wants to create, but a different uuid.
                    # It is a simultaneous creation : rename local's datablock. Remote will do the same thing on its side
                    # and we will end up will all renamed datablocks
                    unique_name = f"{existing_datablock.name}_{existing_datablock.mixer_uuid}"
                    logger.warning(
                        f"create_standalone_datablock: Creation name conflict. Renamed existing bpy.data.{self.collection_name}[{existing_datablock.name}] into {unique_name}"
                    )

                    # Rename local's and issue a rename command
                    renames.append(
                        (
                            existing_datablock.mixer_uuid,
                            existing_datablock.name,
                            unique_name,
                            f"Conflict bpy.data.{self.collection_name}[{self.data('name')}] into {unique_name}",
                        )
                    )
                    existing_datablock.name = unique_name

                    datablock = specifics.bpy_data_ctor(self.collection_name, self, context)
                else:
                    # a creation for a datablock that we already have. This should not happen
                    logger.error(f"create_standalone_datablock: unregistered uuid for {self}")
                    logger.error("... update ignored")
                    return None, None
        else:
            datablock = specifics.bpy_data_ctor(self.collection_name, self, context)

        self._initialized = True
        if datablock is None:
            if self.collection_name != "shape_keys":
                logger.warning(f"Cannot create bpy.data.{self.collection_name}[{self.data('name')}]")
            return None, None

        if DEBUG:
            # TODO LIB
            # Detect a failure to avoid spontaneous renames ??
            name = self.data("name")
            if self.collection.get(name).name != datablock.name:
                logger.error(f"Name mismatch after creation of bpy.data.{self.collection_name}[{name}] ")

        datablock.mixer_uuid = self.mixer_uuid
        return self._save(datablock, context), renames

    def _save(self, datablock: T.ID, context: Context) -> T.ID:
        datablock = self._pre_save(datablock, context)
        if datablock is None:
            logger.warning(f"DatablockProxy.update_standalone_datablock() {self} pre_save returns None")
            return None, None
        try:
            context.visit_state.datablock_proxy = self
            for k, v in self._data.items():
                write_attribute(datablock, k, v, context)
        finally:
            context.visit_state.datablock_proxy = None
        self._custom_properties.save(datablock)
        return datablock

    def update_standalone_datablock(self, datablock: T.ID, delta: Delta, context: Context) -> T.ID:
        """
        Update this proxy and datablock according to delta
        """
        datablock = delta.value._pre_save(datablock, context)
        if datablock is None:
            logger.warning(f"DatablockProxy.update_standalone_datablock() {self} pre_save returns None")
            return None

        try:
            context.visit_state.datablock_proxy = self
            self.apply(datablock, self.collection, datablock.name, delta, context)
        finally:
            context.visit_state.datablock_proxy = None

        return datablock

    def save(self, attribute: T.ID, unused_parent: T.bpy_struct, unused_key: Union[int, str], context: Context) -> T.ID:
        """
        Save this proxy into an embedded datablock

        Args:
            attribute: the datablock into which this proxy is saved
            unused_parent: the struct that contains the embedded datablock (e.g. a Scene)
            unused_key: the member name of the datablock in parent (e.g. node_tree)
            context: proxy and visit state

        Returns:
            The saved datablock
        """

        # TODO it might be better to load embedded datablocks as StructProxy and remove this method
        # assert self.is_embedded_data, f"save: called {parent}[{key}], which is not standalone"

        datablock = self._pre_save(attribute, context)
        if datablock is None:
            logger.error(f"DatablockProxy.save() get None after _pre_save({attribute})")
            return None

        try:
            context.visit_state.datablock_proxy = self
            for k, v in self._data.items():
                write_attribute(datablock, k, v, context)
        finally:
            context.visit_state.datablock_proxy = None

        return datablock

    def apply(
        self,
        attribute: T.ID,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> StructProxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the struct to update (e.g. a Material instance)
            parent: the attribute that contains attribute (e.g. bpy.data.materials)
            key: the key that identifies attribute in parent (e.g "Material")
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """
        custom_properties_update = delta.value._custom_properties
        if custom_properties_update is not None:
            self._custom_properties = custom_properties_update
            if to_blender:
                custom_properties_update.save(attribute)

        return super().apply(attribute, parent, key, delta, context, to_blender)

    def apply_to_proxy(
        self,
        attribute: T.ID,
        delta: DeltaUpdate,
        context: Context,
    ):
        """
        Apply delta to this proxy without updating the value of the Blender attribute it manages.

        This method is used in the depsgraph update callback, after the Blender attribute value has been updated by
        the user.

        Args:
            attribute: the datablock that is managed by this proxy
            delta: the delta to apply
            context: proxy and visit state
        """
        collection = getattr(bpy.data, self.collection_name)
        self.apply(attribute, collection, attribute.name, delta, context, to_blender=False)

    def update_soa(self, bl_item, path: Path, soa_members: List[SoaMember]):

        r = self.find_by_path(bl_item, path)
        if r is None:
            return
        container, container_proxy = r
        for soa_member in soa_members:
            soa_proxy = container_proxy.data(soa_member[0])
            soa_proxy.save_array(container, soa_member[0], soa_member[1])

        # HACK force updates :
        if isinstance(bl_item, T.Mesh):
            bl_item.update()
        elif isinstance(bl_item, T.Curve):
            bl_item.twist_mode = bl_item.twist_mode

    def diff(self, attribute: T.ID, key: Union[int, str], prop: T.Property, context: Context) -> Optional[Delta]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        Args:
            attribute: the datablock to update (e.g. a Material instance)
            key: the key that identifies attribute in parent (e.g "Material")
            prop: the Property of struct as found in its enclosing object
            context: proxy and visit state
        """

        # Create a proxy that will be populated with attributes differences.
        diff = self.__class__()
        diff.init(attribute)

        context.visit_state.datablock_proxy = diff
        try:
            delta = self._diff(attribute, key, prop, context, diff)
        finally:
            context.visit_state.datablock_proxy = None

        # compute the custom properties update
        if not isinstance(delta, DeltaReplace):
            custom_properties_update = self._custom_properties.diff(attribute)
            if custom_properties_update is not None:
                if delta is None:
                    # regular diff had found no delta: create one
                    delta = DeltaUpdate(diff)
                diff._custom_properties = custom_properties_update

        return delta

    def _pre_save(self, target: T.bpy_struct, context: Context) -> T.ID:
        return specifics.pre_save_datablock(self, target, context)
