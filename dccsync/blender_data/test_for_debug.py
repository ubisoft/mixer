import unittest
import sys
import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from dccsync.blender_data.proxy import (
    BpyBlendProxy,
    BpyStructProxy,
    BpyIDProxy,
    BpyIDRefProxy,
    BpyPropertyGroupProxy,
    is_pointer_to,
    all_properties,
    LoadElementAs,
    load_as_what,
)
from dccsync.blender_data.diff import BpyBlendDiff
from dccsync.blender_data.filter import default_context


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

    # @unittest.skip("")
    def test_scene(self):
        scene = self.proxy._data["scenes"]._data["Scene_0"]._data
        self.assertEqual(49, len(scene))

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
        # More to understand than to actually test
        all_properties._props.clear()

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

        # The type of a collection element : Scene.objects is a T.Object
        objects_rna_property = T.Scene.bl_rna.properties["objects"]
        self.assertNotEqual(objects_rna_property.fixed_type, T.Object)
        # ... but ...
        self.assertIs(objects_rna_property.fixed_type.bl_rna, T.Object.bl_rna)

    def test_load_as(self):
        self.assertEqual(LoadElementAs.STRUCT, load_as_what(T.Scene, T.Scene.bl_rna.properties["animation_data"]))
        self.assertEqual(LoadElementAs.ID_REF, load_as_what(T.Scene, T.Scene.bl_rna.properties["objects"]))
        self.assertEqual(LoadElementAs.ID_DEF, load_as_what(T.Scene, T.Scene.bl_rna.properties["collection"]))

    def test_pointer_class(self):
        collection = T.Scene.bl_rna.properties["collection"]
        self.assertTrue(is_pointer_to(collection, T.Collection))
        node_tree = T.World.bl_rna.properties["node_tree"]
        self.assertTrue(is_pointer_to(node_tree, T.NodeTree))
        self.assertFalse(is_pointer_to(node_tree, T.ShaderNodeTree))

    def test_skip_ShaderNodeTree(self):
        world = D.worlds["World"]
        proxy = BpyStructProxy(world).load(world)
        self.assertTrue("color" in proxy._data)
        self.assertFalse("node_tree" in proxy._data)


def main():
    module = sys.modules[__name__]
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    # suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestCore)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == "__main__":
    unittest.main()
