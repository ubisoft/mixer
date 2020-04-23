from __future__ import annotations
import bpy
import bpy.types as T  # noqa
import mathutils
from typing import Mapping
from uuid import uuid4
import logging

logger = logging.Logger("plop", logging.INFO)


class Proxy:
    _vector_types = {mathutils.Vector, mathutils.Color, mathutils.Quaternion, mathutils.Euler}
    _builtin_types = {float, int, bool, str}

    # _blend_data_types = [t for t in bpy.data.bl_rna.properties.values() if t.bl_rna.identifier == "CollectionProperty"]


class Iter:
    def __init__(self):
        self._gen = self.gen()

    def __next__(self):
        return next(self._gen)

    def __iter__(self):
        return self


class BpyStructProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    # TODO limit depth like in multiuser ?
    # TODO name or class based whitelists and blacklists. These lists could be customized for a given workflow step,
    # TODO attribute groups per UI panel ?

    def __init__(self, blender_type: bpy.types.bpy_struct, *args, **kwargs):
        properties = blender_type.bl_rna.properties.items()

        skip_names = ["rna_type"]

        # We care for some non readonly properties. Collection object are tagged read_only byt can be updated with

        # Beware :

        # >>> bpy.types.Scene.bl_rna.properties['collection']
        # <bpy_struct, PointerProperty("collection")>

        # TODO is_readonly may be only interesting for "base types". FOr Collections it seems always set to true
        # meaning that the collection property slot cannot be updated although the object is mutable
        #
        # TODO make this "static"
        # TODO filter out bpy_func + others
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
        Load a property into a python object of the appropriate type, be ti a Proxy or a native python object
        """

        # TODO should we compare the type (e.g. bpy.types.bpy_prop_collection) or the rna ?
        # TODO why do some types have an rna (T.ID) and not others (T.bpy_prop_collection)

        attr_type = type(attr)
        if attr_type in self._builtin_types:
            return attr
        if attr_type in self._vector_types:
            return list(attr)
        if attr_type is mathutils.Matrix:
            return [list(col) for col in attr.col]
        if attr_type == T.bpy_prop_array:
            return BpyPropArrayProxy().load(attr)
        if attr_type == T.bpy_prop_collection:
            return BpyPropCollectionProxy().load(attr)
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
            # TOTO some attributes not in
            attr_value = self.get(bl_instance, attr_name)
            if attr_value is not None:
                self._data[attr_name] = attr_value
        return self

    def update(self, diff_data: BpyStructDiff):
        pass


class BpyIDProxy(BpyStructProxy):
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

        # TODO do we let this to normal attr sync for initial load ?

        # https://blender.stackexchange.com/questions/55423/how-to-get-the-class-type-of-a-blender-collection-property
        self.dccsync_uuid = bl_instance.dccsync_uuid
        return self

    def update(self, diff_data: BpyIDDiff):
        pass


class IDRefProxy(Proxy):
    """
    A reference to an item of bpy_prop_collection in bpy.data member
    """

    def __init__(self, bl_type):
        self.bl_type = bl_type
        pass

    def load(self, bl_instance):

        # Walk up to child of ID
        class_bl_rna = bl_instance.bl_rna
        while class_bl_rna.base is not None and class_bl_rna.base != bpy.types.ID.bl_rna:
            class_bl_rna = class_bl_rna.base

        # TODO for easier access could keep a red to the BpyBlendProxy
        # TODO maybe this information does not belong to _data and _data should be reserved to "fields"
        self._data = (
            class_bl_rna.identifier,  # blenddata collection
            bl_instance.name_full,  # key in blenddata collection
        )
        return self


def ensure_uuid(item: bpy.types.ID):
    if item.get("dccsync_uuid") is None:
        item.dccsync_uuid = str(uuid4())


# TODO derive from BpyIDProxy
class BpyPropCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of ID in bpy.data. May not work as is for bpy_prop_collection on non-ID
    """

    def __init__(self):
        self._data: Mapping[str, BpyIDProxy] = {}

    class _Iter(Iter):
        # TODO explai why an iterator
        # probalbly no
        def gen(self):
            keep = []
            for name, type_ in bpy.data.bl_rna.properties.items():
                if name not in keep:
                    pass  # continue
                if type_.bl_rna is bpy.types.CollectionProperty.bl_rna:
                    yield name
            raise StopIteration

    def iter_all(self):
        return self._Iter()

    def items(self):
        return self._data.items()

    def load(self, bl_collection: bpy.types.bpy_prop_collection):
        """
        in bl_collection : a bpy.types.bpy_prop_collection
        """
        # TODO check parameter type
        # TODO : beware
        # some are handled by data (real collection)
        # others are not (view_layers, master collections)
        # TODO check that it contains a struct, for instance a MeshVertex
        for name, item in bl_collection.items():
            ensure_uuid(item)
            self._data[name] = BpyIDProxy(item).load(item)

        return self

    def update(self, diff):
        """
        Update the proxy according to the diff
        """
        for name, bl_collection in diff.items_added.items():
            item = bl_collection[name]
            self._data[name] = BpyIDProxy(item).load(item)
        for name in diff.items_removed:
            del self._data[name]
        for old_name, new_name in diff.items_renamed:
            self._data[new_name] = self._data[old_name]
            del self._data[old_name]
        for name, delta in diff.items_updated:
            self._data[name].update(delta)


class BpyPropArrayProxy(Proxy):
    def load(self, bl_array: bpy.types.bpy_prop_array):
        # TODO
        self._data = "array_tbd"


class BpyBlendProxy(Proxy):

    # TODO how could we get this information programatically
    types = {
        "actions": T.Action,
        "armatures": T.Armature,
        "brushes": T.Brush,
        "cache_files": T.CacheFile,
        "cameras": T.Camera,
        "collections": T.Collection,
        "curves": T.Curve,
        "fonts": T.VectorFont,
        "grease_pencils": T.GreasePencil,
        "images": T.Image,
        "lattices": T.Lattice,
        "libraries": T.Library,
        "lightprobess": T.LightProbe,
        "lights": T.Light,
        "linestyles": T.FreestyleLineStyle,
        "masks": T.Mask,
        "materials": T.Material,
        "meshes": T.Mesh,
        "mataballs": T.MetaBall,
        "moveclips": T.MovieClip,
        "node_groups": T.NodeTree,
        "objects": T.Object,
        "paint_curves": T.PaintCurve,
        "palettes": T.Palette,
        "particles": T.ParticleSettings,
        "scenes": T.Scene,
        "screens": T.Screen,
        "shape_keys": T.Key,
        "sounds": T.Sound,
        "speakers": T.Speaker,
        "texts": T.Text,
        "textures": T.Texture,
        "window_managers": T.WindowManager,
        "worlds": T.World,
        "workspaces": T.WorkSpace,
    }

    def __init__(self, *args, **kwargs):
        self._data: Mapping[str, BpyPropCollectionProxy] = {}

    class _Iter(Iter):
        def gen(self):
            keep = []
            for name, type_ in bpy.data.bl_rna.properties.items():
                if name not in keep:
                    pass  # continue
                if type_.bl_rna is bpy.types.CollectionProperty.bl_rna:
                    yield name

    def iter_all(self):
        return self._Iter()

    def load(self):
        for name in self.iter_all():
            collection = getattr(bpy.data, name)
            # the diff may be easier if all the collectiona are always present
            self._data[name] = BpyPropCollectionProxy().load(collection)
        return self

    def update(self, diff):
        for name in self.iter_all():
            deltas = diff.deltas.get(name)
            if deltas is not None:
                self._data[name].update(diff.deltas[name])


class ProxyFactory:
    # TODO split blenddata collections and others
    collections = [bpy.types.BlendDataObjects, bpy.types.BlendDataScenes]
    # root_types = [type, T.bpy_struct_meta_idprop, T.RNAMetaPropGroup]
    root_types = [type, T.bpy_struct_meta_idprop]

    @classmethod
    def make(cls, class_or_instance) -> Proxy:
        param_type = type(class_or_instance)
        if param_type not in cls.root_types:
            class_ = param_type
        else:
            class_ = class_or_instance

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
