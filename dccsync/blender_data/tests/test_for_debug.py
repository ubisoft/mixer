import copy
import functools
import json
from pathlib import Path
import sys
import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from dccsync.blender_data import types
from dccsync.blender_data.blenddata import BlendData
from dccsync.blender_data.json_codec import Codec
from dccsync.blender_data.proxy import (
    BpyBlendProxy,
    BpyStructProxy,
    BpyIDProxy,
    BpyIDRefProxy,
    BpyPropertyGroupProxy,
    LoadElementAs,
    load_as_what,
    write_attribute,
)
from dccsync.blender_data.types import is_builtin, is_vector, is_matrix
from dccsync.blender_data.filter import (
    CollectionFilterOut,
    Context,
    FilterStack,
    TypeFilterIn,
    TypeFilterOut,
    default_context,
    default_filter,
)
from mathutils import Matrix, Vector

this_folder = Path(__file__).parent
test_blend_file = str(this_folder / "test_data.blend")


def register_bl_equals(testcase, context):
    equals = functools.partial(bl_equals, context=context, skip_name=True)
    for type_name in dir(T):
        type_ = getattr(T, type_name)
        testcase.addTypeEqualityFunc(type_, equals)


# @unittest.skip("")
class TestLoadProxy(unittest.TestCase):
    def setUp(self):
        file = str(this_folder / "test_data.blend")
        # file = r"D:\work\data\test_files\BlenderSS 2_82.blend"
        bpy.ops.wm.open_mainfile(filepath=file)
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


def equals(attr_a, attr_b, context=default_context):
    type_a = type(attr_a)
    type_b = type(attr_b)
    if type_a != type_b:
        return False

    if is_builtin(type_a) or is_vector(type_a) or is_matrix(type_a):
        if attr_a != attr_b:
            return False
    elif type_a == T.bpy_prop_array:
        if attr_a != attr_b:
            return False
    elif issubclass(type_a, T.bpy_prop_collection):
        for key in attr_a.keys():
            attr_a_i = attr_a[key]
            attr_b_i = attr_b[key]
            if not equals(attr_a_i, attr_b_i):
                return False
    elif issubclass(type_a, T.bpy_struct):
        for name, _ in context.properties(attr_a.bl_rna):
            attr_a_i = getattr(attr_a, name)
            attr_b_i = getattr(attr_b, name)
            if not equals(attr_a_i, attr_b_i):
                return False
    else:
        raise NotImplementedError

    return True


# context = default_context


def bl_equals(attr_a, attr_b, msg=None, skip_name=False, context=None):
    """
    skip_name for the top level name only since cloned objects have different names
    """
    failureException = unittest.TestCase.failureException
    type_a = type(attr_a)
    type_b = type(attr_b)
    if type_a != type_b:
        raise failureException(f"Different types : {type_a} and {type_b}")
    if is_builtin(type_a) or is_vector(type_a) or is_matrix(type_a):
        if attr_a != attr_b:
            raise failureException(f"Different values : {attr_a} and {attr_b}")
    elif type_a == T.bpy_prop_array:
        if attr_a != attr_b:
            raise failureException(f"Different values for array : {attr_a} and {attr_b}")
    elif issubclass(type_a, T.bpy_prop_collection):
        for key in attr_a.keys():
            attr_a_i = attr_a[key]
            attr_b_i = attr_b[key]
            if not bl_equals(attr_a_i, attr_b_i, msg, skip_name=False, context=context):
                raise failureException(
                    f"Different values for collection items at key {key} : {attr_a_i} and {attr_b_i}"
                )
    elif issubclass(type_a, T.bpy_struct):
        for name, _ in context.properties(attr_a.bl_rna):
            if skip_name and name == "name":
                return True
            attr_a_i = getattr(attr_a, name)
            attr_b_i = getattr(attr_b, name)
            if not bl_equals(attr_a_i, attr_b_i, msg, skip_name=False, context=context):
                raise failureException(
                    f"Different values for collection items at key {name} : {attr_a_i} and {attr_b_i}"
                )
    else:
        raise NotImplementedError

    return True


# @unittest.skip('')
class TestCore(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)
        register_bl_equals(self, default_context)

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
        self.assertTrue(isinstance(T.ShaderNodeTree.bl_rna, T.NodeTree))
        self.assertTrue(isinstance(T.ShaderNodeTree.bl_rna, T.ID))
        self.assertTrue(isinstance(T.ShaderNodeTree.bl_rna, T.bpy_struct))

        self.assertTrue(issubclass(T.Camera, T.Camera))
        self.assertTrue(issubclass(T.Camera, T.ID))
        self.assertTrue(isinstance(T.Camera.bl_rna, T.Camera))
        self.assertTrue(isinstance(T.Camera.bl_rna, T.ID))

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

    def test_check_types(self):
        # check our own assertions about types
        for t in dir(bpy.types):
            for prop in getattr(bpy.types, t).bl_rna.properties.values():
                # All ID are behind pointers or in collections
                self.assertFalse(isinstance(prop.bl_rna, T.ID))

    def test_load_as(self):
        self.assertEqual(LoadElementAs.STRUCT, load_as_what(T.Scene, T.Scene.bl_rna.properties["animation_data"]))
        self.assertEqual(LoadElementAs.ID_REF, load_as_what(T.Scene, T.Scene.bl_rna.properties["objects"]))
        self.assertEqual(LoadElementAs.ID_REF, load_as_what(T.Scene, T.Scene.bl_rna.properties["camera"]))
        self.assertEqual(LoadElementAs.ID_DEF, load_as_what(T.Scene, T.Scene.bl_rna.properties["collection"]))

    def test_pointer_class(self):
        eevee = T.Scene.bl_rna.properties["eevee"]
        self.assertTrue(types.is_pointer_to(eevee, T.SceneEEVEE))

        collection = T.Scene.bl_rna.properties["collection"]
        self.assertTrue(types.is_pointer_to(collection, T.Collection))
        node_tree = T.World.bl_rna.properties["node_tree"]
        self.assertTrue(types.is_pointer_to(node_tree, T.NodeTree))
        self.assertFalse(types.is_pointer_to(node_tree, T.ShaderNodeTree))

        camera = T.Scene.bl_rna.properties["camera"]
        self.assertTrue(types.is_pointer_to(camera, T.Object))

        data = T.Object.bl_rna.properties["data"]
        self.assertTrue(types.is_pointer_to(data, T.ID))

    def test_skip_ShaderNodeTree(self):  # noqa N802
        world = D.worlds["World"]
        proxy = BpyStructProxy().load(world, default_context)
        self.assertTrue("color" in proxy._data)
        # self.assertFalse("node_tree" in proxy._data)

    def test_equals(self):
        self.assertTrue(equals(D, D))
        self.assertTrue(equals(D.objects[0], D.objects[0]))
        self.assertFalse(equals(D.objects[0], D.objects[1]))

    def test_equality_func(self):
        self.assertEqual(D.objects[0], D.objects[0])
        self.assertNotEqual(D.objects[0], D.objects[1])
        self.assertEqual(D.objects, D.objects)
        self.assertEqual(D, D)


def matches_type(p, t):
    # sic ...
    if p.bl_rna is T.CollectionProperty.bl_rna and p.srna and p.srna.bl_rna is t.bl_rna:
        return True


class TestProperties(unittest.TestCase):
    def test_one(self):
        context = default_context
        camera = D.cameras[0]
        props = dict(context.properties(camera))
        self.assertEqual(len(props), 39)
        self.assertIn("cycles", props.keys())
        item = D.cameras[0]
        props = context.properties(item)


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
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)

    def test_one(self):
        blenddata = BlendData.instance()
        scenes = blenddata.collection("scenes").bpy_collection()
        sounds = blenddata.collection("sounds").bpy_collection()
        # identity is not true
        self.assertEqual(scenes, D.scenes)
        self.assertEqual(sounds, D.sounds)
        self.assertIs(scenes["Scene_0"], D.scenes["Scene_0"])


class TestCodec(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)
        self.proxy = BpyBlendProxy()
        self.proxy.load(default_context)
        register_bl_equals(self, default_context)

    def test_object(self):
        bl_cam = D.cameras["Camera_0"]
        cam = self.proxy._data["cameras"]._data["Camera_0"]
        self.assertIsInstance(cam, BpyIDProxy)
        codec = Codec()
        s = codec.encode(cam)
        o = json.loads(s)
        print(json.dumps(o, sort_keys=True, indent=4))
        o2 = codec.decode(s)
        self.assertEqual(cam, o2)
        o2.save(bl_cam)
        pass

    def test_cam(self):
        cam_sent = D.cameras["Camera_0"]
        cam_proxy_sent = self.proxy._data["cameras"]._data["Camera_0"]
        self.assertIsInstance(cam_proxy_sent, BpyIDProxy)
        codec = Codec()
        message = codec.encode(cam_proxy_sent)
        # transmit
        cam_proxy_received = codec.decode(message)
        cam_proxy_received._data["name"] = "cam_received"
        cam_received = D.cameras.new("cam_received")
        cam_proxy_received.save(cam_received)
        self.assertEqual(cam_sent, cam_received)
        pass


def clone(src):
    dst = src.__class__()
    for k, v in dir(src):
        setattr(dst, k, v)
    return dst


class TestWriteAttribute(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)
        self.proxy = BpyBlendProxy()
        self.proxy.load(default_context)
        register_bl_equals(self, default_context)

    def test_write_simple_types(self):
        scene = D.scenes[0]
        object_ = D.objects[0]
        # matrix = [10.0, 20.0, 30.0, 40.0, 11.0, 21.0, 31.0, 41.0, 12.0, 22.0, 32.0, 42.0, 14.0, 24.0, 34.0, 44]
        matrix2 = [[10.0, 20.0, 30.0, 40], [11.0, 21.0, 31.0, 41], [12.0, 22.0, 32.0, 42], [14.0, 24.0, 34.0, 44]]
        values = [
            # (scene, "name", "Plop"),
            (scene, "frame_current", 99),
            (scene, "use_gravity", False),
            (scene, "gravity", [-1, -2, -3]),
            (scene, "gravity", Vector([-10, -20, -30])),
            (scene, "sync_mode", "FRAME_DROP"),
            # (object_, "matrix_world", matrix),
            (object_, "matrix_world", Matrix(matrix2)),
        ]
        for bl_instance, name, value in values:
            write_attribute(name, value, bl_instance)
            stored_value = getattr(bl_instance, name)
            stored_type = type(stored_value)
            self.assertEqual(stored_type(value), stored_value)

    def test_write_bpy_struct(self):
        scene = D.scenes[0]
        eevee_proxy = self.proxy._data["scenes"]._data["Scene_0"]._data["eevee"]
        eevee_proxy._data["gi_cubemap_resolution"] = "64"
        eevee_proxy.save(scene.eevee)
        self.assertEqual("64", scene.eevee.gi_cubemap_resolution)

    def test_write_bpy_property_group(self):
        # Not very useful it derives from struct
        scene = D.scenes[0]
        cycles_proxy = self.proxy._data["scenes"]._data["Scene_0"]._data["cycles"]
        cycles_proxy._data["shading_system"] = True
        cycles_proxy.save(scene.cycles)
        self.assertEqual(True, scene.cycles.shading_system)

    def test_write_array_of_struct_with_vec(self):
        # self.addTypeEqualityFunc(D.bpy_struct, bl_equalityfunc)
        cube = D.meshes["Cube"]
        vertices_proxy = self.proxy._data["meshes"]._data["Cube"]._data["vertices"]
        co_proxy = vertices_proxy._data[0]._data["co"]
        co_proxy[0] *= 2
        co_proxy[1] *= 2
        co_proxy[2] *= 2
        vertices_proxy.save(cube.vertices)
        self.assertEqual(cube.vertices[0].co, Vector(co_proxy))

    # explicit test per data type , including addition in collections

    def test_write_light(self):
        light_name = "Light"
        light = D.lights["Light"]
        clone_name = f"Clone of {light_name}"
        light_proxy = self.proxy._data["lights"]._data[light_name]
        expected_energy = 666
        light_proxy._data["energy"] = expected_energy
        light_type = light_proxy._data["type"]
        light_proxy._data["name"] = clone_name
        clone = D.lights.new(clone_name, light_type)
        light_proxy.save(clone)
        self.assertEqual(light.energy, expected_energy)

    def test_write_scene(self):
        scene_name = "Scene_0"
        scene = D.scenes[scene_name]
        clone_name = f"Clone of {scene_name}"
        scene_proxy = self.proxy._data["scenes"]._data[scene_name]
        scene_proxy._data["name"] = clone_name
        clone = D.scenes.new(clone_name)
        scene_proxy.save(clone)
        self.assertEqual(scene, clone)


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
