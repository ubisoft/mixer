from __future__ import annotations
import logging
import sys
from typing import Iterable, Mapping, Union
from uuid import uuid4

import bpy
import bpy.types as T  # noqa
import mathutils

logger = logging.Logger("blender_data", logging.INFO)

DEBUG = True

if DEBUG:
    # easier to find circular references
    pass
    # sys.setrecursionlimit(50)

i = 0
all_pointers: Mapping[int, any] = {}
references = []

vector_types = {mathutils.Vector, mathutils.Color, mathutils.Quaternion, mathutils.Euler}
builtin_types = {float, int, bool, str, set}

# TODO unused ?
# those found in bpy_data members
data_types = {
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


def debug_check_stack_overflow(func, *args, **kwargs):
    """
    Use as a function decorator to detect probable stack overflow in case of circular references

    Beware : inspect performance is very poor. 
    sys.setrecursionlimit cannot be used because it will possibly break the Blender VScode
    plugin and StackOverflowException is not caught by VScode "Raised exceptions" breakpoint.
    """

    def wrapper(*args, **kwargs):
        import inspect

        if len(inspect.stack(0)) > 50:
            raise RuntimeError("Possible stackoverflow")
        func(*args, **kwargs)

    return wrapper


def is_a(class_: type, base: type) -> bool:
    # None fot bpy_struct
    base_rna = getattr(base, "bl_rna", None)
    parent = class_.bl_rna.base
    while parent is not None:
        if parent == base_rna:
            return True
        parent = parent.base

    # parent is none means derive from bpy_struct
    return base == T.bpy_struct


def is_data_collection_type(attr):
    has_rna = hasattr(attr, "bl_rna")
    if not has_rna:
        return False
    # Find if collection element type derives from ID.  Do now know how to get the element type
    # from the collection attribute, so list types that contain "links" into a blenddata collection.
    # TODO and others
    data_types = {T.BlendDataObjects.bl_rna, T.SceneObjects.bl_rna, T.LayerObjects.bl_rna}
    return attr.bl_rna in data_types


# @debug_check_stack_overflow
def read_attribute(attr: any, attr_property: any):
    """
        Load a property into a python object of the appropriate type, be ti a Proxy or a native python object
    """

    # TODO should we compare the type (e.g. bpy.types.bpy_prop_collection) or the rna ?
    # TODO why do some types have an rna (T.ID) and not others (T.bpy_prop_collection)

    attr_type = type(attr)
    if attr_type in builtin_types:
        return attr
    if attr_type in vector_types:
        return list(attr)
    if attr_type is mathutils.Matrix:
        return [list(col) for col in attr.col]

    # We have tested the types that are usefully reported by the python binding, now harder work.
    # These were implemented first and may be better implemented with the bl_rna property of the parent struct
    if attr_type == T.bpy_prop_array:
        return BpyPropArrayProxy().load(attr)

    if attr_type == T.bpy_prop_collection:
        # TODO redo properly, not hardcoded
        if is_data_collection_type(attr):
            return BpyPropDataCollectionProxy().load_as_IDref(attr)
        else:
            return BpyPropStructCollectionProxy().load(attr)

    if isinstance(attr_property, T.CollectionProperty):
        return BpyPropStructCollectionProxy().load(attr)

    # We have handles "simple" cases
    bl_rna = attr_property.bl_rna
    if bl_rna is None:
        logger.warning("Skipping attribute %s", attr)
        return None

    if is_a(attr_type, T.ID):
        # Handling
        # if it is an ID, do not crate a proxy but link through its data collection
        # an IDRef whe the bpy contain IDdef
        # TODO this is false for ShaderNodeTree contained in materials, that do not seem to be stored in BlendData
        return BpyIDRefProxy(attr_type).load(attr)

    if DEBUG:
        dbg_detect_duplicate_pointer = False
        if dbg_detect_duplicate_pointer and isinstance(attr_property, T.PointerProperty):
            # Debugging : figure out if two PointerProperty can point to the same objects, except for ID in blenddata
            # Some are duplicate. In this case the default behavior would be to duplicate the object, maybe not appropriate
            ptr = attr.as_pointer()
            if ptr in all_pointers:
                logging.warning(f"duplicate pointer {hex(ptr)} for {attr} from {all_pointers[ptr]}")
            all_pointers[ptr] = attr

    if is_a(attr_type, T.PropertyGroup):
        return BpyPropertyGroupProxy(attr_type).load(attr)

    if is_a(attr_type, T.bpy_struct):
        return BpyStructProxy(attr_type.bl_rna).load(attr)

    if isinstance(attr_property, T.PointerProperty):
        assert references.pop() == attr.as_pointer()

    raise ValueError(f"Unsupported attribute type {attr_type} without bl_rna for attribute {attr} ")


class Proxy:
    pass


class Iter:
    # Attempt to iterate the same way during load and diff.
    # currently not used
    def __init__(self):
        self._gen = self.gen()

    def __next__(self):
        return next(self._gen)

    def __iter__(self):
        return self


ignores = {bpy.types.Scene: {"objects"}}


class Properties:
    _props: Mapping[any, Iterable[str]] = {}

    # Always excluded
    _exclude_names = {
        "type_info",  # for Available (?) keyingset
        "depsgraph",  # found in Viewlayer
        "rna_type",
        "is_evaluated",
        "original",
        "users",
        "use_fake_user",
        "tag",
        "is_library_indirect",
        "library",
        "override_library",
        "preview",
        "dccsync_uuid",
    }

    # Always excluded
    _exclude_types = {
        # A pointer in f-curve point to a recursive infinite structure
        # T.PointerProperty
        # TODO currently work only with plain attributes, not collections
        # TODO Handle properly a circular reference between FCurve.group and ActionGroup.channels that must be handled
        T.FCurve,
        T.ShaderNodeTree,
    }

    def exclude(self, bl_type, property_name: str, property_type) -> bool:
        name_excludes = property_name in self._exclude_names
        if name_excludes:
            return True
        type_excludes = any([isinstance(property_type, t) for t in self._exclude_types])
        # debug
        for t in self._exclude_types:
            if isinstance(property_type, t):
                logging.warning(f"Excluded {t} from {bl_type}.{property_name}, points to {property_type.fixed_type}")
        return type_excludes

    def properties(self, bl_type: any):
        props = self._props.get(bl_type)
        if props is None:
            props = {
                name: property_
                for name, property_ in bl_type.bl_rna.properties.items()
                if not self.exclude(bl_type, name, property_)
            }
            self._props[bl_type] = props
        return props


all_properties = Properties()


class StructLikeProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    # TODO limit depth like in multiuser. Anyhow, there are circular references in f-curves
    # TODO name or class based whitelists and blacklists. These lists could be customized for a given workflow step,
    # TODO filter on attribute groups per UI panel ?

    def __init__(self, bl_struct: Union[T.bpy_struct, T.PropertyGroup], *args, **kwargs):

        # We care for some non readonly properties. Collection object are tagged read_only byt can be updated with

        # Beware :

        # >>> bpy.types.Scene.bl_rna.properties['collection']
        # <bpy_struct, PointerProperty("collection")>

        # TODO is_readonly may be only interesting for "base types". FOr Collections it seems always set to true
        # meaning that the collection property slot cannot be updated although the object is mutable
        #
        # TODO make this "static"
        # TODO filter out bpy_func + others
        self._bl_rna_properties = all_properties.properties(bl_struct.bl_rna)

        # TODO we also care for some readonly properties that are in fact links to data collections
        # TODO can we have ID ad members ?
        # These ara for the type and should be loaded once for all
        self.bl_rna_attributes = self._bl_rna_properties.keys()

        # pointers are the links to other datablocks (e.g. camera)
        self._data = {}
        pass

    def get(self, bl_instance: any, attr_name: str, attr_property: any):

        if attr_name == "cycles":
            breakpoint
        attr = getattr(bl_instance, attr_name)
        if attr is None:
            return None
        return read_attribute(attr, attr_property)

    def load(self, bl_instance: any):
        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        for attr_name, attr_property in self._bl_rna_properties.items():
            # TOTO some attributes not in
            attr_value = self.get(bl_instance, attr_name, attr_property)
            if attr_value is not None:
                self._data[attr_name] = attr_value
        return self

    def update(self, diff_data: BpyStructDiff):
        pass


class BpyPropertyGroupProxy(StructLikeProxy):
    pass


class BpyStructProxy(StructLikeProxy):
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


class BpyIDRefProxy(Proxy):
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


class BpyPropStructCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of non-ID in bpy.data
    """

    def __init__(self):
        self._data: Mapping[Union[str, int], BpyIDProxy] = {}

    class _Iter(Iter):
        # TODO explain why an iterator
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
        # TODO : some are handled by data (real collection)
        # others are not (view_layers, master collections)

        # TODO check that it contains a struct, for instance a MeshVertex
        # when iterating over items(), the keys may be a name (str) or an index (int)

        # TODO also check for element type to skip

        for key, item in bl_collection.items():
            self._data[key] = BpyStructProxy(item).load(item)

        return self

    def update(self, diff):
        """
        Update the proxy according to the diff
        """
        # TODO


# TODO derive from BpyIDProxy
class BpyPropDataCollectionProxy(Proxy):
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

    def load_as_ID(self, bl_collection: bpy.types.bpy_prop_collection):
        """
        Load bl_collection elements as plain IDs, with all element properties. Use this lo load from bpy.data
        """
        for name, item in bl_collection.items():
            ensure_uuid(item)
            self._data[name] = BpyIDProxy(item).load(item)
        return self

    def load_as_IDref(self, bl_collection: bpy.types.bpy_prop_collection):
        """
        Load bl_collection elements as referenced into bpy.data
        """
        for name, item in bl_collection.items():
            self._data[name] = BpyIDRefProxy(item).load(item)
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
    # TODO blenddata is a struct so use BpyStructProxy instead
    # like BpyStructProxy(bpy.data).load(bpy.data)

    def __init__(self, *args, **kwargs):
        self._data: Mapping[str, BpyPropDataCollectionProxy] = {}

    class _Iter(Iter):
        def gen(self):
            keep = ["scenes"]
            keep = []
            exclude = [
                # "brushes" generates harmless warnings when EnumProperty properties are initialized with a value not in the enum
                "brushes",
                # TODO actions require to handle the circular reference between ActionGroup.channel and FCurve.group
                "actions",
                # we do not need those
                "screens",
                "window_managers",
                "workspaces",
            ]
            for name, type_ in bpy.data.bl_rna.properties.items():
                if name in exclude:
                    continue
                if name not in keep:
                    # TODO properly filter
                    pass
                if type_.bl_rna is bpy.types.CollectionProperty.bl_rna:
                    yield name

    def iter_all(self):
        return self._Iter()

    def load(self):
        global all_pointers
        all_pointers.clear()

        for name in self.iter_all():
            collection = getattr(bpy.data, name)
            # the diff may be easier if all the collectiona are always present
            self._data[name] = BpyPropDataCollectionProxy().load_as_ID(collection)
        all_pointers.clear()
        assert len(references) == 0
        return self

    def update(self, diff):
        for name in self.iter_all():
            deltas = diff.deltas.get(name)
            if deltas is not None:
                self._data[name].update(diff.deltas[name])
