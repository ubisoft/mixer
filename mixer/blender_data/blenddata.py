import functools
import logging
from typing import Any, List, Mapping, Union

import bpy
import bpy.types as T  # noqa N812

logger = logging.Logger(__name__, logging.INFO)


def bl_rna_to_type(bl_rna):
    return getattr(T, bl_rna.identifier)


# Map root collection name to object type
# e.g. "objects" -> bpy.types.Object, "lights" -> bpy.types.Light, ...
collection_name_to_type = {
    p.identifier: bl_rna_to_type(p.fixed_type)
    for p in T.BlendData.bl_rna.properties
    if p.bl_rna.identifier == "CollectionProperty"
}

# Map object type name to root collection
# e.g. "Object" -> "objects", "Light" -> "lights"
rna_identifier_to_collection_name = {value.bl_rna.identifier: key for key, value in collection_name_to_type.items()}

load_ctors = ["fonts", "movieclips", "sounds"]


class BlendDataCollection:
    """
    Wrapper to any of the collections inside bpy.blenddata
    """

    def __init__(self, name: str, bpy_data_collection):
        self._name = name
        self._dirty: bool = True
        self._bpy_data_collection = bpy_data_collection
        self._items = {}

        if self._name in load_ctors:
            ctor_name = "load"
        else:
            ctor_name = "new"
        self._ctor = getattr(self._bpy_data_collection, ctor_name, None)
        self._ctor_name = ctor_name

    def __getitem__(self, key):
        return self.get()[key]

    def name(self):
        return self._name

    def bpy_collection(self):
        return self._bpy_data_collection

    def get(self):
        if not self._dirty:
            return self._items
        self._items = {x.name_full: x for x in self._bpy_data_collection}
        self._dirty = False
        return self._items

    def ctor(self, name: str, ctor_args: List[Any] = ()) -> Union[T.ID, None]:
        """
        Create an instance in the BlendData collection using its ctor (new, load, ...)
        """
        if self._ctor is None:
            logger.warning("unexpected call to BlendDataCollection.ctor() for %s", self._bpy_data_collection)
            # Should not appen
            return None
        data = self._items.get(name)
        if data is None:
            try:
                data = self._ctor(name, *ctor_args)
            except TypeError:
                logging.error(f"Exception while calling ctor {self.name()}.{self._ctor_name}({name}, {ctor_args})")
            self._items[name] = data
        return data

    def remove(self, name_full):
        collection = self._items[name_full]
        # do something else for scenes
        self._bpy_data_collection.remove(collection)
        del self._items[name_full]
        self._dirty = True

    def rename(self, old_name, new_name):
        item = self._items[old_name]
        item.name = new_name
        del self._items[old_name]
        self._items[new_name] = item

    def set_dirty(self):
        self._dirty = True

    def clear(self):
        self._data.clear()
        self._dirty = True


class BlendData:
    """
    Wrapper to bpy.data, with linear time access to collection items by name.

    These objects keep live reference to Blender blenddata collection, so they must not be used after the
    file has been reloaded, hence the handler below.
    """

    def __init__(self):
        self.reset()

    @classmethod
    @functools.lru_cache(1)
    def instance(cls):
        """
        Work around a situation where a BlendData object cannot be initialized during addon loading because an exception
        is thrown like in
        https://blender.stackexchange.com/questions/8702/attributeerror-restrictdata-object-has-no-attribute-filepath
        but about bpy.data
        """

        # In the end this is very messy. This structure is to avoid hadcoding information about Blenddata.
        # The trouble is that during addon loading, getattr(bpy.data, 'cameras') will fail with error
        #   AttributeError: '_RestrictData' object has no attribute 'cameras'
        # So any python module that instanciates this class at the module level will cause the error

        return cls()

    def reset(self):
        _bpy_collections = {name: getattr(bpy.data, name) for name in collection_name_to_type.keys()}
        self._collection_names = {collection: name for name, collection in _bpy_collections.items()}
        self._collections = {
            name: BlendDataCollection(name, _bpy_collections[name]) for name in collection_name_to_type.keys()
        }

        # "Object": "objects"
        self._collections_name_from_inner_identifier: Mapping[str, str] = {
            type_.bl_rna.identifier: name for name, type_ in collection_name_to_type.items()
        }

    def __getitem__(self, attrname):
        return self._collections[attrname].get()

    def set_dirty(self):
        for data in self._collections.values():
            data.set_dirty()

    def clear(self):
        for data in self._collections.values():
            data.clear()

    def collection_name(self, collection: T.bpy_prop_collection) -> str:
        return self._collection_names[collection]

    def collection(self, collection_name: str) -> BlendDataCollection:
        return self._collections[collection_name]

    def bpy_collection(self, collection_name: str) -> T.bpy_prop_collection:
        return self._collections[collection_name].bpy_collection()

    def bl_collection_name_from_inner_identifier(self, type_identifier: str) -> str:
        """
        Blenddata collection from the name of the inner type (e.g. 'Object', 'Light')
        """
        return self._collections_name_from_inner_identifier[type_identifier]

    def bl_collection_name_from_ID(self, id: T.ID) -> str:  # noqa N802
        """
        Blenddata collection from an Id.
        """
        # Find the topmost type below ID, e.g. Light for AreaLight
        bl_rna = id.bl_rna
        while bl_rna is not None and bl_rna.base.bl_rna is not bpy.types.ID.bl_rna:
            bl_rna = bl_rna.base
        if bl_rna is None:
            return None
        type_identifier = bl_rna.identifier
        return self._collections_name_from_inner_identifier[type_identifier]


@bpy.app.handlers.persistent
def on_load(dummy):
    BlendData.instance().reset()


def register():
    for t in collection_name_to_type.values():
        t.mixer_uuid = bpy.props.StringProperty(default="")

    # unfortunately cannot use reset during plugin load/unload
    bpy.app.handlers.load_post.append(on_load)


def unregister():
    bpy.app.handlers.load_post.remove(on_load)
