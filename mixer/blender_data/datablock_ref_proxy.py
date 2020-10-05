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
from typing import Any, Dict, Optional, TYPE_CHECKING, Union

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.attributes import read_attribute
from mixer.blender_data.blenddata import rna_identifier_to_collection_name
from mixer.blender_data.proxy import DeltaUpdate, Proxy
from mixer.blender_data.struct_proxy import StructProxy
from mixer.blender_data.types import bases_of

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Uuid, VisitState

logger = logging.getLogger(__name__)


class DatablockRefProxy(Proxy):
    """
    A reference to a standalone datablock

    Examples of such references are :
    - Camera.dof.focus_object
    """

    def __init__(self):
        self._datablock_uuid: str = None
        # Not used but "required" by the json codec
        self._data: Dict[str, Any] = {}
        self._bpy_data_collection: str = None
        self._initial_name: str = None

        self._debug_name = None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._datablock_uuid}, bpy.data.{self._bpy_data_collection}, name at creation: {self._initial_name})"

    def display_string(self) -> str:
        return f"bpy.data.{self._bpy_data_collection}[{self._initial_name}]"

    @property
    def mixer_uuid(self) -> Uuid:
        return self._datablock_uuid

    def is_none(self) -> bool:
        """
        Returns True if the reference is None (like if Scene.camera is not set)
        """

        return not self._datablock_uuid

    def load(self, datablock: T.ID, visit_state: VisitState) -> DatablockRefProxy:
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

    def save(self, container: Union[T.ID, T.bpy_prop_collection], key: str, visit_state: VisitState):
        """
        Save the datablock reference represented by this proxy into a datablock member (Scene.camera)
        or a collection item (Scene.collection.children["Collection"])
        """
        ref_target = self.target(visit_state)
        # make sure to differentiate actual None value and unresolved ref
        if ref_target is None:
            logger.info(f"Unresolved reference {container}.{key} -> {self.display_string()}]")
        if isinstance(container, T.bpy_prop_collection):
            # reference stored in a collection
            # is there a case for this is is always link() in DatablockCollectionProxy ?
            if isinstance(key, str):
                try:
                    if ref_target is None:
                        visit_state.unresolved_refs.append(
                            self.mixer_uuid, lambda datablock: container.__setitem__(key, datablock)
                        )
                    else:
                        container[key] = ref_target
                except TypeError as e:
                    logger.warning(
                        f"DatablockRefProxy.save() exception while saving {ref_target} into {container}[{key}]..."
                    )
                    logger.warning(f"...{e}")
            else:
                # is there a case for this ?
                logger.warning(
                    f"Not implemented: DatablockRefProxy.save() for IDRef into collection {container}[{key}]"
                )
        else:
            # reference stored in a struct (e.g. Object.parent)
            if not container.bl_rna.properties[key].is_readonly:
                try:
                    # This is what saves Camera.dof.focus_object
                    if ref_target is None:
                        visit_state.unresolved_refs.append(
                            self.mixer_uuid, lambda datablock: setattr(container, key, datablock)
                        )
                    else:
                        setattr(container, key, ref_target)
                except Exception as e:
                    logger.warning(f"write attribute skipped {key} for {container}...")
                    logger.warning(f" ...Error: {repr(e)}")

    def target(self, visit_state: VisitState) -> Optional[T.ID]:
        """
        The datablock referenced by this proxy
        """
        datablock = visit_state.ids.get(self._datablock_uuid)
        if datablock is None:
            # HACK
            # We are trying to find the target of a datablock reference like Object.mesh and the datablock
            # is not known to the proxy state (visit_state). This occurs when the target datablock is of
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
                logger.warning(
                    f"Fetching datablock by name found datablock {datablock} with uuid {datablock.mixer_uuid}"
                )
                return None
            datablock.mixer_uuid = self._datablock_uuid
            visit_state.ids[self._datablock_uuid] = datablock
            logger.warning(f"{self}: registering {datablock}")

        return datablock

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> StructProxy:
        """
        Apply a delta to this proxy, which occurs when Scene.camera changes, for instance
        """
        update: DatablockRefProxy = delta.value
        if to_blender:
            if update.is_none():
                setattr(parent, key, None)
            else:
                assert type(update) == type(self), "type(update) == type(self)"
                assert (
                    self.is_none() or self._bpy_data_collection == update._bpy_data_collection
                ), "self.is_none() or self._bpy_data_collection == update._bpy_data_collection"

                datablock = visit_state.ids.get(update._datablock_uuid)
                setattr(parent, key, datablock)
        return update

    def diff(self, datablock: T.ID, datablock_property: T.Property, visit_state: VisitState) -> Optional[DeltaUpdate]:
        """
        Computes the difference between this proxy and its Blender state.
        """

        if datablock is None:
            return DeltaUpdate(DatablockRefProxy())

        value = read_attribute(datablock, datablock_property, visit_state)
        assert isinstance(value, DatablockRefProxy)
        if value._datablock_uuid != self._datablock_uuid:
            return DeltaUpdate(value)
        else:
            return None
