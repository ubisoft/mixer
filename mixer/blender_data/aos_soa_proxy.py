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
from typing import List, Dict, Optional, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa
import mathutils

from mixer.blender_data.proxy import Proxy
from mixer.blender_data.types import is_vector

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context


logger = logging.getLogger(__name__)

# in sync with soa_initializers
soable_properties = {
    T.BoolProperty,
    T.IntProperty,
    T.FloatProperty,
    mathutils.Vector,
    mathutils.Color,
    mathutils.Quaternion,
}

# in sync with soa_initializers
soa_initializers = {
    bool: array.array("b", [0]),
    int: array.array("l", [0]),
    float: array.array("f", [0.0]),
    mathutils.Vector: array.array("f", [0.0]),
    mathutils.Color: array.array("f", [0.0]),
    mathutils.Quaternion: array.array("f", [0.0]),
}


# TODO : is there any way to find these automatically ? Seems easy to determine if a struct is simple enough so that
# an array of struct can be loaded as an Soa. Is it worth ?
# Beware that MeshVertex must be handled as SOA although "groups" is a variable length item.
# Enums are not handled by foreach_get()
soable_collection_properties = {
    T.GPencilStroke.bl_rna.properties["points"],
    T.GPencilStroke.bl_rna.properties["triangles"],
    T.Mesh.bl_rna.properties["edges"],
    T.Mesh.bl_rna.properties["face_maps"],
    T.Mesh.bl_rna.properties["loops"],
    T.Mesh.bl_rna.properties["loop_triangles"],
    T.Mesh.bl_rna.properties["polygons"],
    T.Mesh.bl_rna.properties["polygon_layers_float"],
    T.Mesh.bl_rna.properties["polygon_layers_int"],
    T.Mesh.bl_rna.properties["vertices"],
    # messy: :MeshPolygon.vertices has variable length, not 3 as stated in the doc, so ignore
    # T.Mesh.bl_rna.properties["polygons"],
    T.MeshUVLoopLayer.bl_rna.properties["data"],
    T.MeshLoopColorLayer.bl_rna.properties["data"],
}


def is_soable_collection(prop):
    return prop in soable_collection_properties


def is_soable_property(bl_rna_property):
    return any(isinstance(bl_rna_property, soable) for soable in soable_properties)


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
        item_bl_rna,
        attr_name: str,
        context: Context,
    ):
        """
        - bl_collection: a collection of structure, e.g. T.Mesh.vertices
        - item_bl_rna: the bl_rna if the structure contained in the collection, e.g. T.MeshVertices.bl_rna
        - attr_name: a member if the structure to be loaded as a sequence, e.g. "groups"
        """

        logger.warning(f"Not implemented. Load AOS  element for {bl_collection}.{attr_name} ")
        return self

        # The code below was initially written for MeshVertex.groups, but MeshVertex.groups is updated
        # via Object.vertex_groups so it is useless in this case. Any other usage ?

        # self._data.clear()
        # attr_property = item_bl_rna.properties[attr_name]
        # # A bit overkill:
        # # for T.Mesh.vertices[...].groups, generates a StructCollectionProxy per Vertex even if empty
        # self._data[MIXER_SEQUENCE] = [
        #     read_attribute(getattr(item, attr_name), attr_property, synchronized_properties, visit_context) for item in bl_collection
        # ]
        # return self

    def save(self, bl_collection: bpy.types.bpy_prop_collection, attr_name: str, context: Context):

        logger.warning(f"Not implemented. Save AOS  element for {bl_collection}.{attr_name} ")

        # see comment in load()

        # sequence = self._data.get(MIXER_SEQUENCE)
        # if sequence is None:
        #     return

        # if len(sequence) != len(bl_collection):
        #     # Avoid by writing SOA first ? Is is enough to resize the target
        #     logger.warning(
        #         f"Not implemented. Save AO size mistmatch (incoming {len(sequence)}, target {len(bl_collection)}for {bl_collection}.{attr_name} "
        #     )
        #     return

        # for i, value in enumerate(sequence):
        #     target = bl_collection[i]
        #     write_attribute(target, attr_name, value)


class SoaElement(Proxy):
    """
    A structure member inside a bpy_prop_collection loaded as a structure of array element

    For instance, Mesh.vertices[].co is loaded as an SoaElement of Mesh.vertices. Its _data is an array
    """

    def __init__(self):
        self._buffer: Optional[array.array] = None

    def load(
        self, parent: bpy.types.bpy_prop_collection, element_name: str, prototype_item: T.bpy_struct, context: Context
    ):
        """
        Args:
            parent : The collection that contains this element (e.g.  a_mesh.vertices, a_mesh.edges, ...)
            attr_name : The name of this element (e.g, "co", "normal", ...)
            prototype_item : an element pf parent collection
        """

        # TODO: bool

        # Determine what type and length of buffer we need
        # TODO do not reallocate on re-read
        attr = getattr(prototype_item, element_name)
        element_type = type(attr)
        array_size = len(parent)
        if is_vector(element_type):
            array_size *= len(attr)
        elif element_type is T.bpy_prop_array:
            array_size *= len(attr)
            element_type = type(attr[0])

        typecode = soa_initializers[element_type].typecode
        buffer = self._buffer
        if buffer is None or buffer.buffer_info()[1] != array_size or buffer.typecode != typecode:
            self._buffer = soa_initializer(element_type, array_size)

        # if foreach_get() raises "RuntimeError: internal error setting the array"
        # it means that the array is ill-formed.
        # Check rna_access.c:rna_raw_access()
        parent.foreach_get(element_name, self._buffer)

        # Store the buffer information at the root of the datablock so that it is easy to find it for serialization
        visit_state = context.visit_state
        parent_path = tuple(visit_state.path)
        datablock_proxy = visit_state.datablock_proxy
        datablock_proxy._soas[parent_path].append((element_name, self))

        return self

    def save(self, bl_instance: T.bpy_prop_collection, attr_name: str, context: Context):
        # This code is reached during save() of MeshVertex, but the data is in a SOA command
        # that will be received later and processed with save_buffer()
        pass

    def save_buffer(self, bl_collection: T.bpy_prop_collection, attr_name, buffer: array.array):
        # TODO : serialization currently not performed
        self._buffer = buffer
        try:
            bl_collection.foreach_set(attr_name, buffer)
        except RuntimeError as e:
            logger.error(f"saving soa {bl_collection}.{attr_name} failed")
            logger.error(f"... member size: {len(bl_collection)}, array: ('{buffer.typecode}', {len(buffer)})")
            logger.error(f"... exception {e}")
