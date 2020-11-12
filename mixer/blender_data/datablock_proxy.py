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
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.blenddata import rna_identifier_to_collection_name

from mixer.blender_data.attributes import apply_attribute, read_attribute, write_attribute
from mixer.blender_data.proxy import DeltaUpdate
from mixer.blender_data.struct_proxy import StructProxy
from mixer.blender_data.types import sub_id_type
from mixer.local_data import get_source_file_path

if TYPE_CHECKING:
    import array
    from mixer.blender_data.bpy_data_proxy import RenameChangeset, Context, VisitState
    from mixer.blender_data.aos_soa_proxy import SoaElement


DEBUG = True

logger = logging.getLogger(__name__)


class DatablockProxy(StructProxy):
    """
    Proxy to a datablock, standalone (bpy.data.cameras['Camera']) or embedded.
    """

    def __init__(self):
        super().__init__()

        self._bpy_data_collection: str = None
        """name of the bpy.data collection this datablock belongs to, None if embedded in another datablock"""

        self._class_name: str = ""
        self._datablock_uuid: Optional[str] = None

        self._soas: Dict[VisitState.Path, List[Tuple[str, SoaElement]]] = defaultdict(list)
        """e.g. {
            ("vertices"): [("co", co_soa), ("normals", normals_soa)]
            ("edges"): ...
        }"""

        self._media: Optional[Tuple[str, bytes]] = None

    def init(self, datablock: T.ID):
        if datablock is not None:
            if not datablock.is_embedded_data:
                type_name = sub_id_type(type(datablock)).bl_rna.identifier
                self._bpy_data_collection = rna_identifier_to_collection_name[type_name]
                self._datablock_uuid = datablock.mixer_uuid
            self._class_name = datablock.__class__.__name__

    @classmethod
    def make(cls, attr_property):

        if isinstance(attr_property, T.Mesh):
            from mixer.blender_data.mesh_proxy import MeshProxy

            return MeshProxy()
        return DatablockProxy()

    @property
    def is_standalone_datablock(self):
        return self._bpy_data_collection is not None

    @property
    def is_embedded_data(self):
        return self._bpy_data_collection is None

    def mixer_uuid(self) -> Optional[str]:
        return self._datablock_uuid

    def rename(self, new_name: str):
        self._data["name"] = new_name
        self._data["name_full"] = new_name

    def __str__(self) -> str:
        return f"DatablockProxy {self.mixer_uuid()} for bpy.data.{self.collection_name}[{self.data('name')}]"

    def load(
        self,
        bl_instance: T.ID,
        key: str,
        context: Context,
        bpy_data_collection_name: str = None,
    ):
        """
        Load a datablock into this proxy
        """
        if bl_instance.is_embedded_data and bpy_data_collection_name is not None:
            logger.error(
                f"DatablockProxy.load() for {bl_instance} : is_embedded_data is True and bpy_prop_collection is {bpy_data_collection_name}. Item ignored"
            )
            return

        if bl_instance.is_embedded_data:
            self._bpy_data_collection = None

        if bpy_data_collection_name is not None:
            self._bpy_data_collection = bpy_data_collection_name

        self._class_name = bl_instance.__class__.__name__
        self._data.clear()
        properties = context.synchronized_properties.properties(bl_instance)
        # this assumes that specifics.py apply only to ID, not Struct
        properties = specifics.conditional_properties(bl_instance, properties)
        try:
            context.visit_state.datablock_proxy = self
            for name, bl_rna_property in properties:
                attr = getattr(bl_instance, name)
                attr_value = read_attribute(attr, name, bl_rna_property, context)
                # Also write None values to reset attributes like Camera.dof.focus_object
                # TODO for scene, test difference, only send update if dirty as continuous updates to scene
                # master collection will conflicting writes with Master Collection
                self._data[name] = attr_value
        finally:
            context.visit_state.datablock_proxy = None

        specifics.post_save_id(self, bl_instance)

        uuid = bl_instance.get("mixer_uuid")
        if uuid:
            # It is a bpy.data ID, not an ID "embedded" inside another ID, like scene.collection
            id_ = context.proxy_state.datablocks.get(uuid)
            if id_ is not bl_instance:
                # this occurs when
                # - when we find a reference to a BlendData ID that was not loaded
                # - the ID are not properly ordred at creation time, for instance (objects, meshes)
                # instead of (meshes, objects) : a bug
                logger.debug("DatablockProxy.load(): %s not in context.proxy_state.datablocks[uuid]", bl_instance)
            self._datablock_uuid = bl_instance.mixer_uuid
            context.proxy_state.proxies[uuid] = self

        self.attach_media_descriptor(bl_instance)
        return self

    def attach_media_descriptor(self, datablock: T.ID):
        # if Image, Sound, Library, MovieClip, Text, VectorFont, Volume
        # create a self._media with the data to be sent
        # - filepath
        # - reference to the packed data if packed
        #
        #
        if isinstance(datablock, T.Image):
            path = get_source_file_path(datablock.filepath)
            packed_file = datablock.packed_file
            data = None
            if packed_file is not None:
                data = packed_file.data
            else:
                with open(bpy.path.abspath(path), "rb") as data_file:
                    data = data_file.read()
            self._media = (path, data)

    @property
    def collection_name(self) -> Optional[str]:
        """
        The name of the bpy.data collection this object is a proxy, None if an embedded ID
        """
        return self._bpy_data_collection

    @property
    def collection(self) -> T.bpy_prop_collection:
        return getattr(bpy.data, self.collection_name)

    def target(self, context: Context) -> T.ID:
        return context.proxy_state.datablocks.get(self.mixer_uuid())

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
        existing_datablock = self.collection.get(incoming_name)
        if existing_datablock:
            if not existing_datablock.mixer_uuid:
                # A datablock created by VRtist command in the same command batch
                # Not an error, we will make it ours by adding the uuid and registering it
                logger.info(f"create_standalone_datablock for {self} found existing datablock from VRtist")
                datablock = existing_datablock
            else:
                if existing_datablock.mixer_uuid != self.mixer_uuid():
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

        if datablock is None:
            logger.warning(f"Cannot create bpy.data.{self.collection_name}[{self.data('name')}]")
            return None, None

        if DEBUG:
            name = self.data("name")
            if self.collection.get(name).name != datablock.name:
                logger.error(f"Name mismatch after creation of bpy.data.{self.collection_name}[{name}] ")

        datablock.mixer_uuid = self.mixer_uuid()

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

        return datablock, renames

    def update_standalone_datablock(self, datablock: T.ID, delta: DeltaUpdate, context: Context) -> T.ID:
        """
        Update this proxy and datablock according to delta
        """
        datablock = delta.value._pre_save(datablock, context)
        if datablock is None:
            logger.warning(f"DatablockProxy.update_standalone_datablock() {self} pre_save returns None")
            return None

        try:
            context.visit_state.datablock_proxy = self
            self.apply(self.collection, datablock.name, delta, context)
        finally:
            context.visit_state.datablock_proxy = None

        return datablock

    def save(self, bl_instance: Any = None, attr_name: str = None, context: Context = None) -> T.ID:
        """
        Save this proxy into an existing datablock that may be a bpy.data member item or an embedded datablock
        """
        collection_name = self.collection_name
        if collection_name is not None:
            logger.info(f"IDproxy save standalone {self}")
            # a standalone datablock in a bpy.data collection

            if bl_instance is None:
                bl_instance = self.collection
            if attr_name is None:
                attr_name = self.data("name")
            id_ = bl_instance.get(attr_name)

            if id_ is None:
                logger.warning(f"IDproxy save standalone {self}, not found. Creating")
                id_ = specifics.bpy_data_ctor(collection_name, self, context)
                if id_ is None:
                    logger.warning(f"Cannot create bpy.data.{collection_name}[{attr_name}]")
                    return None
                if DEBUG:
                    if bl_instance.get(attr_name) != id_:
                        logger.error(f"Name mismatch after creation of bpy.data.{collection_name}[{attr_name}] ")
                id_.mixer_uuid = self.mixer_uuid()
        else:
            logger.info(f"IDproxy save embedded {self}")
            # an is_embedded_data datablock. pre_save will retrieve it by calling target
            id_ = getattr(bl_instance, attr_name)
            pass

        target = self._pre_save(id_, context)
        if target is None:
            logger.warning(f"DatablockProxy.save() {bl_instance}.{attr_name} is None")
            return None

        try:
            context.visit_state.datablock_proxy = self
            for k, v in self._data.items():
                write_attribute(target, k, v, context)
        finally:
            context.visit_state.datablock_proxy = None

        return target

    def apply_to_proxy(
        self,
        datablock: T.ID,
        delta: Optional[DeltaUpdate],
        context: Context,
    ):
        """
        Apply delta to this proxy, but do not update Blender state
        """
        if delta is None:
            return

        update = delta.value
        assert type(update) == type(self)
        try:
            context.visit_state.datablock_proxy = self
            for k, delta in update._data.items():
                try:
                    current_value = self._data.get(k)
                    self._data[k] = apply_attribute(datablock, k, current_value, delta, context, to_blender=False)
                except Exception as e:
                    logger.warning(f"apply_to_proxy(). Processing {delta}")
                    logger.warning(f"... for {datablock}.{k}")
                    logger.warning(f"... Exception: {e!r}")
                    logger.warning("... Update ignored")
                    continue
        finally:
            context.visit_state.datablock_proxy = None

    def update_soa(self, bl_item, path: List[Union[int, str]], soas: List[Tuple[str, array.array]]):

        r = self.find_by_path(bl_item, path)
        if r is None:
            return
        container, container_proxy = r
        for element_name, buffer in soas:
            soa_proxy = container_proxy.data(element_name)
            soa_proxy.save_array(container, element_name, buffer)

        # HACK
        if isinstance(bl_item, T.Mesh):
            bl_item.update()

        # HACK 2 (force update curves)
        if isinstance(bl_item, T.Curve):
            bl_item.twist_mode = bl_item.twist_mode

    def diff(self, datablock: T.ID, key: str, prop: T.Property, context: Context) -> Optional[DeltaUpdate]:
        try:
            diff = self.__class__()
            diff.init(datablock)
            context.visit_state.datablock_proxy = diff
            return self._diff(datablock, key, prop, context, diff)
        finally:
            context.visit_state.datablock_proxy = None

    def _pre_save(self, target: T.bpy_struct, context: Context) -> T.ID:
        return specifics.pre_save_datablock(self, target, context)
