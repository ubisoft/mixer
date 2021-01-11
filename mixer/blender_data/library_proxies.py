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
Utility proxy classes

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import cast, Dict, Optional, Tuple, TYPE_CHECKING, Union

import bpy
import bpy.path
import bpy.types as T  # noqa

from mixer.blender_data.proxy import Delta, DeltaUpdate
from mixer.blender_data.datablock_proxy import DatablockProxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context, Uuid

logger = logging.getLogger(__name__)


class LibraryProxy(DatablockProxy):
    """Proxy for Library datablocks."""

    def __init__(self):
        super().__init__()

        self._indirect_datablocks: Dict[str, Uuid] = {}
        """Uuids to assign to indirect link datablocks after their creation."""
        # TODO update this for reload

    def register_indirect(self, identifier: str, uuid: Uuid, context: Context) -> Optional[T.ID]:
        """Registers an indirect link datablock with its uuid."""
        assert identifier not in self._indirect_datablocks or self._indirect_datablocks[identifier] == uuid

        library_datablock = bpy.data.libraries.get(self._data["name"])
        if library_datablock:
            # the library is already loaded: update the linked datablock at once
            for linked_datablock in library_datablock.users_id:
                if repr(linked_datablock) == identifier:
                    logger.warning(f"register indirect for {identifier} {uuid}")
                    linked_datablock.mixer_uuid = uuid
                    if isinstance(linked_datablock, T.Object):
                        context.proxy_state.register_object(linked_datablock)
                    return linked_datablock

        # the library is not already loaded, register the indirect datablock for update after the library is loaded.
        # this occurs when the indirect datablock (e.g. a Camera) is received before the Object that references it
        logger.warning(f"register indirect: delayed for {identifier} {uuid}")
        self._indirect_datablocks[identifier] = uuid
        return None

    def create_standalone_datablock(self, context: Context):
        # No datablock is created at this point.
        # The Library datablock will be created when the linked datablock is loaded (see load_library_item)
        return None, None

    def load_library_item(self, collection_name: str, datablock_name: str, context: Context) -> T.ID:
        # TODO LIB check relative path
        library_path = bpy.path.abspath(self._data["filepath"])
        logger.warning(f"load_library_item(): {library_path} {collection_name} {datablock_name}")

        # this creates the Library datablock on first load.
        with bpy.data.libraries.load(library_path, link=True) as (data_from, data_to):
            setattr(data_to, collection_name, [datablock_name])

        library_name = self._data["name"]
        library = bpy.data.libraries[library_name]
        library.mixer_uuid = self.mixer_uuid

        # update the uuids of indirect link datablocks that may have been created during the load step
        for linked_datablock in library.users_id:
            identifier = repr(linked_datablock)
            uuid = self._indirect_datablocks.get(identifier)
            if uuid:
                logger.warning(f"register indirect at load {identifier} {uuid}")
                linked_datablock.mixer_uuid = uuid
                context.proxy_state.datablocks[uuid] = linked_datablock
                del self._indirect_datablocks[identifier]

        return getattr(data_to, collection_name)[0]

    def load(self, datablock: T.ID, context: Context) -> LibraryProxy:
        logger.warning(f"load(): {datablock}")
        super().load(datablock, context)
        return self

    def save(self, unused_attribute, parent: T.bpy_struct, key: Union[int, str], context: Context):
        """"""
        # Nothing to save to Blender when the LibraryProxy is received.
        # The Library datablock will be created when the linked datablock is loaded (see load_library_item)
        pass

    def apply(
        self,
        attribute: Union[T.bpy_struct, T.bpy_prop_collection],
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ):

        """
        Apply delta to an attribute with None value.

        This is used for instance Scene.camera is None and update to hold a valid Camera reference

        Args:
            attribute: the Blender attribute to update (e.g a_scene.camera)
            parent: the attribute that contains attribute (e.g. a Scene instance)
            key: the key that identifies attribute in parent (e.g; "camera").
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update attribute in addition to this Proxy
        """
        raise NotImplementedError("LibraryProxy.apply()")
        return self

    def diff(
        self,
        container: Union[T.bpy_prop_collection, T.Struct],
        key: Union[str, int],
        prop: T.Property,
        context: Context,
    ) -> Optional[DeltaUpdate]:
        raise NotImplementedError("LibraryProxy.diff()")
        return None


class DatablockLinkProxy(DatablockProxy):
    """Proxy for direct or indirect linked datablock"""

    # TODO or use mro in serialization ?
    _serialize = DatablockProxy._serialize + ("_library_uuid", "_is_library_indirect", "_name", "_identifier")

    def __init__(self):
        super().__init__()

        self._library_uuid: Uuid = ""
        """Uuid of the library datablock"""

        self._name = ""
        """Name of the datablock in the library"""

        self._identifier = ""
        """repr() value for the datablock, used as identifier to """

        self._is_library_indirect = False

    @property
    def is_library_indirect(self):
        return self._is_library_indirect

    def create_standalone_datablock(self, context: Context) -> Tuple[Optional[T.ID], None]:
        """
        Save this proxy into its target standalone datablock
        """
        from mixer.blender_data.library_proxies import LibraryProxy

        library_proxy = cast(LibraryProxy, context.proxy_state.proxies[self._library_uuid])
        logger.warning(
            f"_create(): {self} library: {library_proxy.data('name')}, indirect: {self._is_library_indirect}"
        )

        if self._is_library_indirect:
            # Indirect linked datablock are created implicitely during the load() of their parent. Keep track of
            # them in order to assign them a uuid after their creation. A uuid is required because they can be
            # referenced by non linked datablocks after load (e.g. a linked Camera referenced by the main Scene)
            link_datablock = library_proxy.register_indirect(self._identifier, self.mixer_uuid, context)
            return link_datablock, None
        else:
            try:
                link_datablock = library_proxy.load_library_item(self._bpy_data_collection, self._name, context)
            except Exception as e:
                logger.error(
                    f"load_library {library_proxy.data('name')} failed for {self._bpy_data_collection}[{self._name}]..."
                )
                logger.error(f"... {e!r}")
                return None, None

            link_datablock.mixer_uuid = self.mixer_uuid
            if isinstance(link_datablock, T.Object):
                context.proxy_state.register_object(link_datablock)
            return link_datablock, None

    def load(self, datablock: T.ID, context: Context) -> DatablockLinkProxy:
        """
        Load the attribute Blender struct into this proxy

        Args:
            attribute: the Blender set to load into this proxy
        """
        assert datablock.library is not None

        # Do not load the attributes
        self._library_uuid = datablock.library.mixer_uuid
        self._is_library_indirect = datablock.is_library_indirect
        self._name = datablock.name
        self._identifier = repr(datablock)

        if isinstance(datablock, T.Object):
            context.proxy_state.register_object(datablock)

        logger.warning(f"load(): {datablock}")
        return self

    def apply(
        self,
        attribute,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> DatablockLinkProxy:
        """
        Apply delta to this proxy and optionally to the Blender attribute its manages.

        Args:
            attribute: the Blender attribute to update
            parent: the attribute that contains attribute
            key: the key that identifies attribute in parent
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update the managed Blender attribute in addition to this Proxy
        """
        return self

    def diff(
        self, attribute, unused_key: Union[int, str], unused_prop: T.Property, unused_context: Context
    ) -> Optional[Delta]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        Args:
            attribute: the set to update (e.g. a the "delimit" attribute of a DecimateModifier instance)
            unused_key: the key that identifies attribute in parent (e.g "delimit")
            unused_prop: the Property of attribute as found in its parent attribute
            unused_context: proxy and visit state
        """
        pass
