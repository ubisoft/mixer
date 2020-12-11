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
Proxy of a reference to datablock

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.attributes import read_attribute
from mixer.blender_data.blenddata import rna_identifier_to_collection_name
from mixer.blender_data.proxy import Delta, DeltaUpdate, Proxy
from mixer.blender_data.type_helpers import bases_of

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Uuid, Context
    from mixer.blender_data.misc_proxies import NonePtrProxy


logger = logging.getLogger(__name__)


class DatablockRefProxy(Proxy):
    """
    A reference to a standalone datablock

    Examples of such references are :
    - Camera.dof.focus_object
    """

    _serialize = ("_bpy_data_collection", "_datablock_uuid", "_initial_name")

    def __init__(self):
        self._datablock_uuid: str = None
        self._bpy_data_collection: str = ""
        self._initial_name: str = None

        self._debug_name = None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._datablock_uuid}, bpy.data.{self._bpy_data_collection}, name at creation: {self._initial_name})"

    def display_string(self) -> str:
        return f"bpy.data.{self._bpy_data_collection}[{self._initial_name}]"

    @property
    def mixer_uuid(self) -> Uuid:
        return self._datablock_uuid

    def load(self, datablock: T.ID, key: Union[int, str], context: Context) -> DatablockRefProxy:
        """
        Load a reference to a standalone datablock into this proxy
        """
        assert not datablock.is_embedded_data

        # see HACK in target()
        # Base type closest to ID (e.g. Light for Point)
        type_ = bases_of(type(datablock).bl_rna)[-2]
        type_name = type_.bl_rna.identifier
        self._bpy_data_collection = rna_identifier_to_collection_name[type_name]
        self._initial_name = datablock.name

        self._datablock_uuid = datablock.mixer_uuid

        self._debug_name = str(datablock)
        return self

    def save(
        self,
        unused_attribute,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        context: Context,
    ):
        """
        Save the datablock reference tracked by this proxy into parent.key or parent[key]

        Args:
            unused_attribute:
            parent: the structure or collection that contains the target reference (e.g. a Scene instance)
            key: the name of the bpy_collection (e.g "camera")
            context: the proxy and visit state
        """
        ref_target = self.target(context)
        if ref_target is None:
            logger.info(f"Unresolved reference {parent}.{key} -> {self.display_string()}]")

        if isinstance(parent, T.bpy_prop_collection):
            # reference stored in a collection
            # is there a case for this is is always link() in DatablockCollectionProxy ?
            if isinstance(key, str):
                try:
                    if ref_target is None:
                        context.proxy_state.unresolved_refs.append(
                            self.mixer_uuid, lambda datablock: parent.__setitem__(key, datablock)
                        )
                    else:
                        parent[key] = ref_target
                except TypeError as e:
                    logger.warning(
                        f"DatablockRefProxy.save() exception while saving {ref_target} into {parent}[{key}]..."
                    )
                    logger.warning(f"...{e!r}")
            else:
                # is there a case for this ?
                logger.warning(f"Not implemented: DatablockRefProxy.save() for IDRef into collection {parent}[{key}]")
        else:
            assert isinstance(key, str)
            # reference stored in a struct (e.g. Object.parent)
            if not parent.bl_rna.properties[key].is_readonly:
                try:
                    # This is what saves Camera.dof.focus_object
                    if ref_target is None:
                        context.proxy_state.unresolved_refs.append(
                            self.mixer_uuid, lambda datablock: setattr(parent, key, datablock)
                        )
                    else:
                        setattr(parent, key, ref_target)
                except Exception as e:
                    logger.warning(f"write attribute skipped {key} for {parent}...")
                    logger.warning(f" ...Error: {repr(e)}")

    def target(self, context: Context) -> Optional[T.ID]:
        """
        The datablock referenced by this proxy
        """
        datablock = context.proxy_state.datablocks.get(self._datablock_uuid)
        if datablock is None:
            # HACK
            # We are trying to find the target of a datablock reference like Object.mesh and the datablock
            # is not known to the proxy state (context). This occurs when the target datablock is of
            # un unsynchronized type (Mesh, currently). If the datablock can be found by name, consider
            # it was created under the hood by a VRtist command and register it.
            collection = getattr(bpy.data, self._bpy_data_collection, None)
            if collection is None:
                logger.warning(f"{self}: reference to unknown collection bpy.data.{self._bpy_data_collection}")
                return None

            datablock = collection.get(self._initial_name)
            if datablock is None:
                return None

            if datablock.mixer_uuid != "":
                logger.error(f"{self}: found datablock with uuid in bpy.data.{self._bpy_data_collection}")
                logger.error(f'... "{self._bpy_data_collection}" may be missing from clear_scene_contents()')
                return None

            datablock.mixer_uuid = self._datablock_uuid
            context.proxy_state.datablocks[self._datablock_uuid] = datablock
            logger.warning(f"{self}: registering {datablock}")

        return datablock

    def apply(
        self,
        attribute,
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> Union[NonePtrProxy, DatablockRefProxy]:
        """
        Apply a delta to this proxy, which occurs when Scene.camera changes, for instance
        """
        update = delta.value
        if to_blender:
            from mixer.blender_data.misc_proxies import NonePtrProxy

            if isinstance(update, NonePtrProxy):
                value = None
            else:
                assert type(update) == type(self), "type(update) == type(self)"

                value = context.proxy_state.datablocks.get(update._datablock_uuid)

            if isinstance(key, int):
                parent[key] = value
            else:
                setattr(parent, key, value)

        return update

    def diff(
        self, datablock: T.ID, key: Union[int, str], datablock_property: T.Property, context: Context
    ) -> Optional[DeltaUpdate]:
        """
        Computes the difference between this proxy and its Blender state.
        """

        if datablock is None:
            from mixer.blender_data.misc_proxies import NonePtrProxy

            return DeltaUpdate(NonePtrProxy())

        value = read_attribute(datablock, key, datablock_property, context)
        assert isinstance(value, DatablockRefProxy)
        if value._datablock_uuid != self._datablock_uuid:
            return DeltaUpdate(value)
        else:
            return None
