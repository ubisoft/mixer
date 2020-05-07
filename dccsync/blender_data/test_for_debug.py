import copy
import sys
import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from dccsync.blender_data import types
from dccsync.blender_data.blenddata import BlendData
from dccsync.blender_data.proxy import (
    BpyBlendProxy,
    BpyStructProxy,
    BpyIDProxy,
    BpyIDRefProxy,
    BpyPropertyGroupProxy,
    LoadElementAs,
    load_as_what,
)

from dccsync.blender_data.filter import (
    CollectionFilterOut,
    Context,
    FilterStack,
    TypeFilterIn,
    TypeFilterOut,
    default_context,
    default_filter,
)


# @unittest.skip("")
class TestLoadProxy(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=".local\\test_data.blend")
        self.proxy = BpyBlendProxy()
        self.proxy.load(default_context)

    def check(self, item, expected_elements):
        self.assertSetEqual(set(item._data.keys()), set(expected_elements))

    # @unittest.skip("")
    def test_blenddata(self):
        blend_data = self.proxy._data
        expected_data = {"scenes", "collections", "objects", "materials", "lights"}
        self.assertTrue(all([e in blend_data.keys() for e in expected_data]))

        self.check(self.proxy._data["scenes"], {"Scene_0", "Scene_1"})
        self.check(self.proxy._data["cameras"], {"Camera_0", "Camera_1"})
        self.check(self.proxy._data["objects"], {"Camera_obj_0", "Camera_obj_1", "Cone", "Cube", "Light"})
        self.check(
            self.proxy._data["collections"], {"Collection_0_0", "Collection_0_1", "Collection_0_0_0", "Collection_1_0"}
        )

    def test_blenddata_filtered(self):
        blend_data = self.proxy._data
        scene = blend_data["scenes"]._data["Scene_0"]._data
        self.assertTrue("eevee" in scene)

        filter_stack = copy.copy(default_filter)
        filter_stack.append({T.Scene: TypeFilterOut(T.SceneEEVEE)})
        proxy = BpyBlendProxy()
        proxy.load(Context(filter_stack))
        blend_data_ = proxy._data
        scene_ = blend_data_["scenes"]._data["Scene_0"]._data
        self.assertFalse("eevee" in scene_)

    # @unittest.skip("")
    def test_scene(self):
        scene = self.proxy._data["scenes"]._data["Scene_0"]._data
        # will vary slightly during tiune tuning of the default filter
        self.assertEqual(50, len(scene))

        objects = scene["objects"]._data
        self.assertEqual(4, len(objects))

        for o in objects.values():
            self.assertEqual(type(o), BpyIDRefProxy, o)

        # builtin attributes (floats)
        frame_properties = [name for name in scene.keys() if name.startswith("frame_")]
        self.assertEqual(9, len(frame_properties))

        # bpy_struct
        eevee = scene["eevee"]._data
        self.assertEqual(59, len(eevee))

        # PropertiesGroup
        cycles_proxy = scene["view_layers"]._data["View Layer"]._data["cycles"]
        self.assertIsInstance(cycles_proxy, BpyPropertyGroupProxy)
        self.assertEqual(32, len(cycles_proxy._data))

        # The master collection
        master_collection = scene["collection"]
        self.assertIsInstance(master_collection, BpyIDProxy)

    def test_collections(self):
        collections = self.proxy._data["collections"]
        coll_0_0 = collections._data["Collection_0_0"]._data

        coll_0_0_children = coll_0_0["children"]
        self.check(coll_0_0_children, {"Collection_0_0_0"})
        for c in coll_0_0_children._data.values():
            self.assertIsInstance(c, BpyIDRefProxy)

        coll_0_0_objects = coll_0_0["objects"]
        self.check(coll_0_0_objects, {"Camera_obj_0", "Camera_obj_1", "Cube", "Light"})
        for o in coll_0_0_objects._data.values():
            self.assertIsInstance(o, BpyIDRefProxy)

        pass


# @unittest.skip('')
class TestCore(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=".local\\test_data.blend")

    def test_issubclass(self):

        # Warning T.bpy_struct is not T.Struct !!
        self.assertTrue(issubclass(T.ID, T.bpy_struct))
        self.assertFalse(issubclass(T.bpy_struct, T.ID))

        self.assertTrue(issubclass(T.StringProperty, T.StringProperty))
        self.assertTrue(issubclass(T.StringProperty, T.Property))
        self.assertTrue(issubclass(T.StringProperty, T.bpy_struct))
        self.assertFalse(issubclass(T.StringProperty, T.ID))

        self.assertTrue(issubclass(T.ShaderNodeTree, T.NodeTree))
        self.assertTrue(issubclass(T.ShaderNodeTree, T.ID))
        self.assertTrue(issubclass(T.ShaderNodeTree, T.bpy_struct))

    def test_invariants(self):
        s = D.scenes[0]

        #
        # same bl_rna in type and property
        self.assertTrue(isinstance(s, T.Scene))
        self.assertIs(T.Scene.bl_rna, s.bl_rna)

        #
        # Pointers
        self.assertTrue(isinstance(s.eevee, T.SceneEEVEE))
        self.assertFalse(isinstance(s.eevee, T.PointerProperty))
        self.assertIsNot(T.Scene.bl_rna.properties["eevee"].bl_rna, s.eevee.bl_rna)
        self.assertIs(T.Scene.bl_rna.properties["eevee"].bl_rna, T.PointerProperty.bl_rna)
        self.assertIs(T.Scene.bl_rna.properties["eevee"].fixed_type.bl_rna, T.SceneEEVEE.bl_rna)
        # readonly pointer with readwrite pointee :
        self.assertTrue(T.Scene.bl_rna.properties["eevee"].is_readonly)
        s.eevee.use_volumetric_shadows = not s.eevee.use_volumetric_shadows
        # readwrite pointer :
        self.assertFalse(T.Scene.bl_rna.properties["camera"].is_readonly)

        #
        # Collection element type
        # The type of a collection element : Scene.objects is a T.Object
        objects_rna_property = T.Scene.bl_rna.properties["objects"]
        self.assertNotEqual(objects_rna_property.fixed_type, T.Object)
        self.assertIs(objects_rna_property.fixed_type.bl_rna, T.Object.bl_rna)
        self.assertIs(T.Mesh.bl_rna.properties["vertices"].srna.bl_rna, T.MeshVertices.bl_rna)

    def test_load_as(self):
        self.assertEqual(LoadElementAs.STRUCT, load_as_what(T.Scene, T.Scene.bl_rna.properties["animation_data"]))
        self.assertEqual(LoadElementAs.ID_REF, load_as_what(T.Scene, T.Scene.bl_rna.properties["objects"]))
        self.assertEqual(LoadElementAs.ID_DEF, load_as_what(T.Scene, T.Scene.bl_rna.properties["collection"]))

    def test_pointer_class(self):
        eevee = T.Scene.bl_rna.properties["eevee"]
        self.assertTrue(types.is_pointer_to(eevee, T.SceneEEVEE))

        collection = T.Scene.bl_rna.properties["collection"]
        self.assertTrue(types.is_pointer_to(collection, T.Collection))
        node_tree = T.World.bl_rna.properties["node_tree"]
        self.assertTrue(types.is_pointer_to(node_tree, T.NodeTree))
        self.assertFalse(types.is_pointer_to(node_tree, T.ShaderNodeTree))

    def test_skip_ShaderNodeTree(self):  # npqa N802
        world = D.worlds["World"]
        proxy = BpyStructProxy(world).load(world, default_context)
        self.assertTrue("color" in proxy._data)
        # self.assertFalse("node_tree" in proxy._data)


def matches_type(p, t):
    # sic ...
    if p.bl_rna is T.CollectionProperty.bl_rna and p.srna and p.srna.bl_rna is t.bl_rna:
        return True


class TestPointerFilterOut(unittest.TestCase):
    def test_exact_class(self):
        filter_stack = FilterStack()
        filter_set = {T.Scene: TypeFilterOut(T.SceneEEVEE)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.SceneEEVEE) for _, p in props]))


class TestTypeFilterIn(unittest.TestCase):
    def test_exact_class(self):
        filter_stack = FilterStack()
        filter_set = {T.BlendData: TypeFilterIn(T.CollectionProperty)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = list(context.properties(T.BlendData))
        self.assertTrue(any([matches_type(p, T.BlendDataCameras) for _, p in props]))
        self.assertFalse(any([matches_type(p, T.StringProperty) for _, p in props]))


class TestCollectionFilterOut(unittest.TestCase):
    def test_exact_class(self):
        filter_stack = FilterStack()
        filter_set = {T.Mesh: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))

    def test_base_class(self):
        filter_stack = FilterStack()
        # Exclude on ID, applies to derived classes
        filter_set = {T.ID: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))

    def test_root_class(self):
        filter_stack = FilterStack()
        # Exclude on all classes
        filter_set = {None: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))

    def test_unrelated_class(self):
        filter_stack = FilterStack()
        # Exclude on unrelated class : does nothing
        filter_set = {T.Collection: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertTrue(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))


class TestBlendData(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=".local\\test_data.blend")

    def test_one(self):
        blenddata = BlendData.instance()
        scenes = blenddata.collection("scenes").bpy_collection()
        sounds = blenddata.collection("sounds").bpy_collection()
        # identity is not true
        self.assertEqual(scenes, D.scenes)
        self.assertEqual(sounds, D.sounds)
        self.assertIs(scenes["Scene_0"], D.scenes["Scene_0"])


def run_tests(test_name: str):
    suite = unittest.defaultTestLoader.loadTestsFromName(test_name)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


def main():
    module = sys.modules[__name__]
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == "__main__":
    unittest.main()
