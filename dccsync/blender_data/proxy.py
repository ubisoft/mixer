import bpy
import mathutils
from uuid import uuid4
from typing import Mapping, Any


vectors = [mathutils.Vector, mathutils.Color, mathutils.Quaternion, mathutils.Euler]


def read(attr):
    if type(attr) is mathutils.Matrix:
        return [list(col) for col in attr.col]
    if type(attr) in vectors:
        return list(attr)
    return attr


class Proxy:
    pass


class BpyStructProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    # TODO limit depth like in multiuser ?
    # TODO name or class based whitelists and blacklists. These lists could be customized for a given workflow step,
    # TODO attribute groups per UI panel ?

    def __init__(self, blender_type: bpy.types.bpy_struct, *args, **kwargs):
        properties = blender_type.bl_rna.properties.items()

        skip = ["data"]
        # We care for non readonly properties
        self._bl_rna_properties = {name: prop for name, prop in properties if not prop.is_readonly and name not in skip}

        # TODO we also care for some readonly properties that are in fact links to data collections
        # TODO can we have ID ad memebers ?
        # These ara for the type and should be loaded once for all
        self.bl_rna_attributes = self._bl_rna_properties.keys()

        # pointers are the links to other datablocks (e.g. camera)
        self._data = {}
        pass

    def get(self, bl_instance, attr_name):
        attr = getattr(bl_instance, attr_name)
        return read(attr)

    def load(self, bl_instance):
        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        for attr in self.bl_rna_attributes:
            self._data[attr] = self.get(bl_instance, attr)
        return self

    def update(self, diff_data):
        pass


class IDProxy(BpyStructProxy):
    """
    Holds a copy of a Blender ID, i.e a type stored in bpy.data, like Object and Material
    """

    def __init__(self, bl_type: bpy.types.ID, *args, **kwargs):
        super().__init__(bl_type, *args, **kwargs)

    def load(self, bl_instance):
        super().load(bl_instance)
        # TODO load the custom properties, probably attributes not in bl_rna_attributes.
        # For instance cyles is a custom property of camera
        # I will not be available is the plugin os not loaded
        return self


class BpyPropCollectionProxy(Proxy):
    def load(self, bl_collection):
        """
        in bl_collection : a bpy..types.bpy_prop_collectiton
        """
        self._data = {k: ProxyFactory.make(v).load(v) for k, v in bl_collection.items()}


class ProxyFactory:
    collections = [bpy.types.BlendDataObjects]

    @classmethod
    def make(cls, class_or_instance) -> Proxy:
        if class_or_instance in cls.collections:
            return BpyPropCollectionProxy()

        bl_rna = class_or_instance.bl_rna
        base = bl_rna.base
        if base == bpy.types.ID.bl_rna:
            # a class handled in bpy.data
            return IDProxy(bl_rna)
        if base is None:
            # a struct
            return BpyStructProxy(bl_rna)
