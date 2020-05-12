import functools

import bpy
import bpy.types as T  # noqa N812

# Map root collection name to object type
# e.g. "objects" -> bpy.types.Object, "lights" -> bpy.types.Light, ...
data_types = {
    p.identifier: getattr(T, p.fixed_type.identifier)
    for p in T.BlendData.bl_rna.properties
    if p.bl_rna.identifier == "CollectionProperty"
}

# Map object type name to root collection
# e.g. "Object" -> "objects", "Light" -> "lights"
rna_identifier_to_collection_name = {value.bl_rna.identifier: key for key, value in data_types.items()}


class BlendDataCollection:
    """
    Wrapper to any of the collections inside bpy.blenddata
    """

    def __init__(self, bpy_data_collection):
        self._dirty: bool = True
        self._bpy_data_collection = bpy_data_collection
        self._items = {}

    def __getitem__(self, key):
        return self._items[key]

    def bpy_collection(self):
        return self._bpy_data_collection

    def get(self):
        if not self._dirty:
            return self._items
        self._items = {x.name_full: x for x in self._bpy_data_collection}
        self._dirty = False
        return self._items

    def new(self, name: str):
        data = self._items.get(name)
        if data is None:
            data = self._bpy_blenddata_collection.new(name)
            self._items[name] = data

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
        return cls()

    def reset(self):
        _bpy_collections = {name: getattr(bpy.data, name) for name in data_types.keys()}
        self._collections = {name: BlendDataCollection(_bpy_collections[name]) for name in data_types.keys()}

    def __getattr__(self, attrname):
        return self._collections[attrname].get()

    def set_dirty(self):
        for data in self._collections.values():
            data.set_dirty()

    def clear(self):
        for data in self._collections.values():
            data.clear()

    def collection(self, collection_name: str):
        return self._collections[collection_name]

    def message_type(self):
        # return backward compatible message type
        pass


@bpy.app.handlers.persistent
def on_load(dummy):
    BlendData.instance().reset()
