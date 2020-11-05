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
This module define Proxy classes and utilities to load array of structures like MeshVertex.vertices
into structure of array and thus benefit from the performance of foreach_get() and foreach_set()
and from the buffer compacity.

This module is not currently used

See synchronization.md
"""
from __future__ import annotations

import array
import logging
from typing import Any, List, Dict, Optional, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa


from mixer.blender_data.proxy import DeltaUpdate, Proxy
from mixer.blender_data.types import is_vector
from mixer.blender_data.specifics import soa_initializers
from mixer.blender_data.attributes import read_attribute, write_attribute

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context


logger = logging.getLogger(__name__)


def soa_initializer(attr_type, length):
    # According to bpy_rna.c:foreach_getset() and rna_access.c:rna_raw_access() implementations,
    # some cases are implemented as memcpy (buffer interface) or array iteration (sequences),
    # with more subcases that require reallocation when the buffer type is not suitable,
    # TODO try to be smart
    element_init = soa_initializers[attr_type]
    if isinstance(element_init, array.array):
        return array.array(element_init.typecode, element_init.tolist() * length)
    elif isinstance(element_init, list):
        return element_init * length


class AosElement(Proxy):
    """
    A structure member inside a bpy_prop_collection loaded as a structure of array element

    For instance, MeshVertex.groups is a bpy_prop_collection of variable size and it cannot
    be loaded as an Soa in Mesh.vertices. So Mesh.vertices loads a "groups" AosElement
    """

    def __init__(self):
        self._data: Dict[str, List] = {}

    def load(
        self,
        bl_collection: bpy.types.bpy_prop_collection,
        attr_name: str,
        attr_property: T.Property,
        context: Context,
    ):
        """
        - bl_collection: a collection of structure, e.g. T.Mesh.vertices
        - item_bl_rna: the bl_rna if the structure contained in the collection, e.g. T.MeshVertices.bl_rna
        - attr_name: a member if the structure to be loaded as a sequence, e.g. "groups"
        """

        for index, item in enumerate(bl_collection):
            self._data[index] = read_attribute(getattr(item, attr_name), index, attr_property, context)

        return self

    def save(self, bl_collection: bpy.types.bpy_prop_collection, attr_name: str, context: Context):
        for index, item in self._data.items():
            write_attribute(bl_collection[index], index, item, context)


class SoaElement(Proxy):
    """
    A structure member inside a bpy_prop_collection loaded as a structure of array element

    For instance, Mesh.vertices[].co is loaded as an SoaElement of Mesh.vertices. Its _data is an array
    """

    _serialize = ("_member_name",)

    def __init__(self):
        self._array: Optional[array.array] = None
        self._member_name: Optional[str] = None

    def array_attr(self, aos: T.bpy_prop_collection, member_name: str, bl_rna: T.bpy_struct):
        prototype_item = getattr(aos[0], member_name)
        member_type = type(prototype_item)

        if is_vector(member_type):
            array_size = len(aos) * len(prototype_item)
        elif member_type is T.bpy_prop_array:
            member_type = type(prototype_item[0])
            if isinstance(bl_rna, T.MeshPolygon) and member_name == "vertices":
                # polygon sizes can differ
                array_size = sum((len(polygon.vertices) for polygon in aos))
            else:
                array_size = len(aos) * len(prototype_item)
        else:
            array_size = len(aos)

        return array_size, member_type

    def load(self, aos: bpy.types.bpy_prop_collection, member_name: str, bl_rna: T.bpy_struct, context: Context):
        """
        Args:
            aos : The array or structures collection that contains this member (e.g.  a_mesh.vertices, a_mesh.edges, ...)
            member_name : The name of this aos member (e.g, "co", "normal", ...)
            prototype_item : an element of parent collection
        """
        array_size, member_type = self.array_attr(aos, member_name, bl_rna)
        typecode = soa_initializers[member_type].typecode
        buffer = self._array
        if buffer is None or buffer.buffer_info()[1] != array_size or buffer.typecode != typecode:
            self._array = soa_initializer(member_type, array_size)

        self._member_name = member_name

        # if foreach_get() raises "RuntimeError: internal error setting the array"
        # it means that the array is ill-formed.
        # Check rna_access.c:rna_raw_access()
        aos.foreach_get(member_name, self._array)
        self._attach(context)
        return self

    def _attach(self, context: Context):
        """Attach the buffer to the DatablockProxy or DeltaUpdate"""
        # Store the buffer information at the root of the datablock so that it is easy to find it for serialization
        visit_state = context.visit_state
        parent_path = tuple(visit_state.path)
        root = visit_state.datablock_proxy
        root._soas[parent_path].append((self._member_name, self))

    def save(self, bl_instance: Any, attr_name: str, context: Context):
        self._member_name = attr_name

    def save_array(self, aos: T.bpy_prop_collection, member_name, array_: array.array):
        if logger.isEnabledFor(logging.DEBUG):
            message = f"save_array {aos}.{member_name}"
            if self._array is not None:
                message += f" proxy ({len(self._array)} {self._array.typecode})"
            message += f" incoming ({len(array_)} {array_.typecode})"
            message += f" blender_length ({len(aos)})"
            logger.debug(message)

        self._array = array_
        try:
            aos.foreach_set(member_name, array_)
        except RuntimeError as e:
            logger.error(f"saving soa {aos}.{member_name} failed")
            logger.error(f"... member size: {len(aos)}, array: ('{array_.typecode}', {len(array_)})")
            logger.error(f"... exception {e!r}")

    def apply(
        self, parent: T.bpy_prop_collection, key: str, delta: Optional[DeltaUpdate], context: Context, to_blender=True
    ) -> SoaElement:
        update = delta.value
        if update is None:
            return self
        self._array = update._array
        if self._member_name != update._member_name:
            logger.error(f"apply: self._member_name != update._member_name {self._member_name} {update._member_name}")
            return self
        return self

    def diff(self, aos: T.bpy_prop_collection, key: str, prop: T.Property, context: Context) -> Optional[DeltaUpdate]:
        if len(aos) == 0:
            return None

        array_size, member_type = self.array_attr(aos, self._member_name, prop.bl_rna)
        typecode = self._array.typecode
        tmp_array = array.array(typecode, soa_initializer(member_type, array_size))
        if logger.isEnabledFor(logging.DEBUG):
            message = (
                f"diff {aos}.{self._member_name} proxy({len(self._array)} {typecode}) blender'{len(aos)} {member_type}'"
            )
            logger.debug(message)
        aos.foreach_get(self._member_name, tmp_array)

        force_diff = context.visit_state.scratchpad.get("force_soa_diff", False)
        if self._array == tmp_array and not force_diff:
            return None

        diff = self.__class__()
        diff._member_name = self._member_name
        diff._array = tmp_array
        diff._attach(context)
        return DeltaUpdate(diff)
