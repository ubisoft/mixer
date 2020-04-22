import bpy
import mathutils
from typing import Mapping, Any

import logging

logger = logging.Logger("plop", logging.INFO)


class Proxy:
    _vector_types = {mathutils.Vector, mathutils.Color, mathutils.Quaternion, mathutils.Euler}
    _builtin_types = {float, int, bool, str}

    # _blend_data_types = [t for t in bpy.data.bl_rna.properties.values() if t.bl_rna.identifier == "CollectionProperty"]


class BpyStructProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    # TODO limit depth like in multiuser ?
    # TODO name or class based whitelists and blacklists. These lists could be customized for a given workflow step,
    # TODO attribute groups per UI panel ?

    def __init__(self, blender_type: bpy.types.bpy_struct, *args, **kwargs):
        properties = blender_type.bl_rna.properties.items()

        skip_names = []

        # We care for some non readonly properties. Collection object are tagged read_only byt can be updated with

        # Beware :

        # >>> bpy.types.Scene.bl_rna.properties['collection']
        # <bpy_struct, PointerProperty("collection")>

        # TODO make this "static"
        self._bl_rna_properties = {
            name: prop for name, prop in properties if (not prop.is_readonly and name not in skip_names)
        }

        # TODO we also care for some readonly properties that are in fact links to data collections
        # TODO can we have ID ad memebers ?
        # These ara for the type and should be loaded once for all
        self.bl_rna_attributes = self._bl_rna_properties.keys()

        # pointers are the links to other datablocks (e.g. camera)
        self._data = {}
        pass

    def read(self, attr):
        """
        Load a property into a python object of the appropriate type
        """
        attr_type = type(attr)
        if attr_type in self._builtin_types:
            return attr
        if attr_type in self._vector_types:
            return list(attr)
        if attr_type is mathutils.Matrix:
            return [list(col) for col in attr.col]
        if attr_type == bpy.types.bpy_prop_array:
            return BpyPropArrayProxy()
        bl_rna = getattr(attr_type, "bl_rna", None)
        if bl_rna is None:
            logging.info("Skip %s", attr)
            return None

        def is_a(class_, base) -> bool:
            parent = class_.bl_rna.base
            while parent is not None:
                if parent == base.bl_rna:
                    return True
                parent = parent.base
            return False

        if is_a(attr_type, bpy.types.ID):
            # warning : identity is false !
            # if it is an ID, do not crate a proxy but link through its data collection
            # an IDRef whe the bpy contain IDdef
            return IDRefProxy(attr_type).load(attr)
        proxy = ProxyFactory.make(attr_type)
        if proxy:
            return proxy.load(attr)
        return attr

    def get(self, bl_instance, attr_name):
        attr = getattr(bl_instance, attr_name)
        if attr is None:
            return None
        return self.read(attr)

    def load(self, bl_instance):
        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        for attr_name in self.bl_rna_attributes:
            attr_value = self.get(bl_instance, attr_name)
            if attr_value is not None:
                self._data[attr_name] = attr_value
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
        # TODO check that bl_instance class derives from ID
        super().load(bl_instance)
        # TODO load the custom properties, probably attributes not in bl_rna_attributes.
        # For instance cyles is a custom property of camera
        # I will not be available is the plugin os not loaded
        return self


class IDRefProxy(Proxy):
    """
    A reference to a member if a blenddata struct
    """

    def __init__(self, bl_type):
        self.bl_type = bl_type
        pass

    def load(self, bl_instance):

        # Walk up to child of ID
        class_bl_rna = bl_instance.bl_rna
        while class_bl_rna.base is not None and class_bl_rna.base != bpy.types.ID.bl_rna:
            class_bl_rna = class_bl_rna.base

        self._data = (
            class_bl_rna.identifier,  # blenddata collection
            bl_instance.name_full,  # key in blenddata collection
        )
        return self


# TODO derive from IDProxy
class BpyPropCollectionProxy(Proxy):
    def load(self, bl_collection):
        """
        in bl_collection : a bpy.types.bpy_prop_collectiton
        """
        # TODO check parameter type
        # TODO : beware
        # some are handled by data (real collection)
        # others are not (view_layers, master collections)
        self._data = {k: IDProxy(v).load(v) for k, v in bl_collection.items()}
        return self


class BpyPropArrayProxy(Proxy):
    def load(self, bl_array: bpy.types.bpy_prop_array):
        # TODO
        self._data = "array_tbd"


class BpyDataProxy(Proxy):
    _data: Mapping[str, BpyPropCollectionProxy] = {}

    def load(self):
        #  bpy.data.worlds.bl_rna == bpy.types.BlendDataWorlds.bl_rna
        for name, type_ in bpy.data.bl_rna.properties.items():
            if type_.bl_rna is bpy.types.CollectionProperty.bl_rna:
                collection = getattr(bpy.data, name)
                # the diff may be easier if all the collectiona are always present
                self._data[name] = BpyPropCollectionProxy().load(collection)
        return self


class ProxyFactory:
    # TODO split blenddata collections and others
    collections = [bpy.types.BlendDataObjects, bpy.types.BlendDataScenes]
    class_likes = [type, bpy.types.bpy_struct_meta_idprop]

    @classmethod
    def make(cls, class_or_instance) -> Proxy:
        param_type = type(class_or_instance)
        if param_type not in cls.class_likes:
            class_ = type(class_or_instance)
        else:
            class_ = class_or_instance

        if class_ in cls.collections:
            return BpyPropCollectionProxy()
        if class_ is bpy.types.bpy_prop_array:
            return BpyPropArrayProxy()

        if getattr(class_, "bl_rna", None) is None:
            breakpoint

        # Do not handle  ID heren, we need to explicitely distinguish ID defs (in blenddata collections) and
        # their references. For instance scene.camera is a reference (an IDRef) to a bpy.data.camaras[] element
        # (an IDRef)
        bl_rna = class_.bl_rna
        if bl_rna.base is None:
            # a struct
            return BpyStructProxy(bl_rna)

        raise ValueError(f"ProxyFactory.make() Unhandled class '{class_}'")
        return None
