from __future__ import annotations
import logging
import sys
from typing import Iterable, Mapping, Union, Any
from uuid import uuid4
from functools import lru_cache
from enum import IntEnum
import bpy
import bpy.types as T  # noqa
import mathutils

logger = logging.Logger(__name__, logging.INFO)

DEBUG = True

if DEBUG:
    # easier to find circular references
    pass
    # sys.setrecursionlimit(50)

i = 0
all_pointers: Mapping[int, any] = {}
references = []

vector_types = {mathutils.Vector, mathutils.Color, mathutils.Quaternion, mathutils.Euler}
builtin_types = {type(None), float, int, bool, str, set}

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

blenddata_types = {t for t in data_types.values()}


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
        return func(*args, **kwargs)

    return wrapper


# an element of T.my_type.bl_rna.properties
RNAProperty = Any


def is_pointer_to(rna_property: RNAProperty, base: type) -> bool:
    return isinstance(rna_property, T.PointerProperty) and isinstance(rna_property.fixed_type, base)


def is_or_points_to(rna_property: RNAProperty, base: type) -> bool:
    return isinstance(rna_property, base) or is_pointer_to(rna_property, base)


class LoadElementAs(IntEnum):
    STRUCT = 0
    ID_REF = 1
    ID_DEF = 2


def same_rna(a, b):
    return a.bl_rna == b.bl_rna


# @lru_cache(maxsize=None)
def load_as_what(parent, attr_property):
    """
    Determine of we must load an attribute as a struct, a blenddata collection element (ID_DEF)
    or a reference to a BlendData collection element (ID_REF)

    All struct are loaded as struct
    All IS are loaded ad D Ref (that is pointer into a blendata collection except
    for specific case. For instance the scene master "collection" is not a D.collections item. 

    Arguments
    parent -- the type that contains the attribute names attr_name, for instance T.Scene
    attr_property -- a bl_rna property of a sttribute, that can be a CollectionProperty or a "plain" attribute
    """
    # In these types, these members are T.ID that to not link to slots in bpy.data collections
    # so we load them as ID and not as a reference to s also in an bpy.data collection
    # Only include here types that derive from ID

    # TODO use T.Material.bl_rna.properties['node_tree'] ...
    force_as_ID_def = {
        T.Material.bl_rna: ["node_tree"],
        T.Scene.bl_rna: ["collection"],
        T.LayerCollection.bl_rna: ["collection"],
    }
    if same_rna(attr_property, T.CollectionProperty) or same_rna(attr_property, T.PointerProperty):
        element_property = attr_property.fixed_type
    else:
        element_property = attr_property

    is_a_blenddata_ID = any([same_rna(element_property, t) for t in blenddata_types])
    if not is_a_blenddata_ID:
        return LoadElementAs.STRUCT

    if attr_property.identifier in force_as_ID_def.get(parent.bl_rna, []):
        return LoadElementAs.ID_DEF
    else:
        return LoadElementAs.ID_REF


# @debug_check_stack_overflow
def read_attribute(attr: any, attr_property: any, parent_struct):
    """
    Load a property into a python object of the appropriate type, be it a Proxy or a native python object


    """

    if attr_property.identifier == "objects":
        breakpoint
        pass

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
        return [e for e in attr]

    if attr_property.identifier == "collection":
        breakpoint
    if attr_type == T.bpy_prop_collection:
        load_as = load_as_what(parent_struct, attr_property)
        if load_as == LoadElementAs.STRUCT:
            return BpyPropStructCollectionProxy().load(attr)
        elif load_as == LoadElementAs.ID_REF:
            return BpyPropDataCollectionProxy().load_as_IDref(attr)
        elif load_as == LoadElementAs.ID_DEF:
            return BpyPropDataCollectionProxy().load_as_ID(attr)

    # TODO merge with previous case
    if isinstance(attr_property, T.CollectionProperty):
        return BpyPropStructCollectionProxy().load(attr)

    bl_rna = attr_property.bl_rna
    if bl_rna is None:
        logger.warning("Unimplemented attribute %s", attr)
        return None

    assert issubclass(attr_type, T.PropertyGroup) == issubclass(attr_type, T.PropertyGroup)
    if issubclass(attr_type, T.PropertyGroup):
        return BpyPropertyGroupProxy(attr_type).load(attr)

    load_as = load_as_what(parent_struct, attr_property)
    if load_as == LoadElementAs.STRUCT:
        return BpyStructProxy(attr_type.bl_rna).load(attr)
    elif load_as == LoadElementAs.ID_REF:
        return BpyIDRefProxy(attr_type).load(attr)
    elif load_as == LoadElementAs.ID_DEF:
        return BpyIDProxy(attr_type).load(attr)

    # assert issubclass(attr_type, T.bpy_struct) == issubclass(attr_type, T.bpy_struct)
    assert False, "unexpected code path"
    # should be handled above
    if issubclass(attr_type, T.bpy_struct):
        return BpyStructProxy(attr_type.bl_rna).load(attr)

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
    _props: Mapping[str, RNAProperty] = {}

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
        # TODO Handle properly a circular reference between FCurve.group and ActionGroup.channels that must be handled
        T.FCurve,
        # TODO a recursion in world nodetrree
        T.NodeTree,
    }

    def exclude(self, property_name: str, rna_property: RNAProperty) -> bool:
        name_excludes = property_name in self._exclude_names
        if name_excludes:
            return True
        type_excludes = any([is_or_points_to(rna_property, t) for t in self._exclude_types])
        return type_excludes

    def properties(self, bl_type: any):
        props = self._props.get(bl_type)
        if props is None:
            props = {
                name: rna_property
                for name, rna_property in bl_type.bl_rna.properties.items()
                if not self.exclude(name, rna_property)
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

    def __init__(self, bl_struct: T.bpy_struct, *args, **kwargs):

        # We care for some non readonly properties. Collection object are tagged read_only byt can be updated with

        # Beware :

        # >>> bpy.types.Scene.bl_rna.properties['collection']
        # <bpy_struct, PointerProperty("collection")>

        # TODO is_readonly may be only interesting for "base types". FOr Collections it seems always set to true
        # meaning that the collection property slot cannot be updated although the object is mutable
        # TODO we also care for some readonly properties that are in fact links to data collections
        # TODO make this "static"
        # TODO filter out bpy_func + others

        # The property information are taken from the containing class, not from the attribute.
        # So we get :
        #   T.Scene.bl_rna.properties['collection']
        #       <bpy_struct, PointerProperty("collection")>
        #   T.Scene.bl_rna.properties['collection'].fixed_type
        #       <bpy_struct, Struct("Collection")>
        # But if we take the information in the attribute we get information for the derferenced
        # data
        #   D.scenes[0].collection.bl_rna
        #       <bpy_struct, Struct("Collection")>
        #
        # We need the former to make a difference betwwen T.Scene.collection and T.Collection.children.
        # the former is a pointer
        self._bl_rna_properties = all_properties.properties(bl_struct.bl_rna)
        self._data = {}
        pass

    def get(self, bl_instance: any, attr_name: str, attr_property: any):
        attr = getattr(bl_instance, attr_name)
        return read_attribute(attr, attr_property, bl_instance)

    def load(self, bl_instance: any):
        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        for attr_name, attr_property in self._bl_rna_properties.items():
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

        # TODO for easier access could keep a ref to the BpyBlendProxy
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
        logger.warning(f"Not implemented {bl_array}")
        self._data = "array_tbd"
        return self


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
