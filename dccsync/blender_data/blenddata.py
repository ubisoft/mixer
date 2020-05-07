import bpy
import bpy.types as T  # noqa N812

blenddata_names = {
    "actions",
    "armatures",
    "brushes",
    "cache_files",
    "cameras",
    "collections",
    "curves",
    "fonts",
    "grease_pencils",
    "images",
    "lattices",
    "libraries",
    "lightprobes",
    "lights",
    "linestyles",
    "masks",
    "materials",
    "meshes",
    "metaballs",
    "movieclips",
    "node_groups",
    "objects",
    "paint_curves",
    "palettes",
    "particles",
    "scenes",
    "screens",
    "shape_keys",
    "sounds",
    "speakers",
    "texts",
    "textures",
    "window_managers",
    "worlds",
    "workspaces",
}

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
    "metaballs": T.MetaBall,
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
    Wrapper to bpy.data, with linear time access to collection items by name
    """

    def __init__(self):
        self._bpy_collections = {name: getattr(bpy.data, name) for name in blenddata_names}
        self.types_rna = [bpy.data.bl_rna.properties[name].fixed_type.bl_rna for name in blenddata_names]
        self._collections = {name: BlendDataCollection(self._bpy_collections[name]) for name in blenddata_names}

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


blenddata = BlendData()
