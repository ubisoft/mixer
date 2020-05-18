import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.proxy import (
    BpyBlendProxy,
    write_attribute,
)
from mixer.blender_data.tests.utils import register_bl_equals, test_blend_file

from mixer.blender_data.filter import default_context
from mathutils import Matrix, Vector


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
            write_attribute(bl_instance, name, value)
            stored_value = getattr(bl_instance, name)
            stored_type = type(stored_value)
            self.assertEqual(stored_type(value), stored_value)

    def test_write_bpy_struct_scene_eevee(self):
        scene = D.scenes[0]
        eevee_proxy = self.proxy._data["scenes"]._data["Scene_0"]._data["eevee"]
        eevee_proxy._data["gi_cubemap_resolution"] = "64"
        eevee_proxy.save(scene, "eevee")
        self.assertEqual("64", scene.eevee.gi_cubemap_resolution)

    def test_write_bpy_property_group_scene_cycles(self):
        # Not very useful it derives from struct
        scene = D.scenes[0]
        cycles_proxy = self.proxy._data["scenes"]._data["Scene_0"]._data["cycles"]
        cycles_proxy._data["shading_system"] = True
        cycles_proxy.save(scene, "cycles")
        self.assertEqual(True, scene.cycles.shading_system)

    def test_write_array_of_struct_with_vec(self):
        # self.addTypeEqualityFunc(D.bpy_struct, bl_equalityfunc)
        cube = D.meshes["Cube"]
        vertices_proxy = self.proxy._data["meshes"]._data["Cube"]._data["vertices"]
        co_proxy = vertices_proxy._data[0]._data["co"]
        co_proxy[0] *= 2
        co_proxy[1] *= 2
        co_proxy[2] *= 2
        vertices_proxy.save(cube, "vertices")
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
        D.lights.new(clone_name, light_type)
        light_proxy.save(D.lights, clone_name)
        self.assertEqual(light.energy, expected_energy)

    def test_write_scene(self):
        scene_name = "Scene_0"
        scene = D.scenes[scene_name]
        clone_name = f"Clone of {scene_name}"
        scene_proxy = self.proxy._data["scenes"]._data[scene_name]
        scene_proxy._data["name"] = clone_name
        clone = D.scenes.new(clone_name)
        scene_proxy.save(D.scenes, clone_name)
        self.assertEqual(scene, clone)

    def test_write_scene_world(self):
        scene_name = "Scene_0"
        scene = D.scenes[scene_name]
        # scene.world = D.worlds["World_1"]
        clone_name = f"Clone of {scene_name}"
        world_proxy = self.proxy._data["scenes"]._data[scene_name]._data["world"]
        clone = D.scenes.new(clone_name)
        world_proxy.save(clone, "world")
        self.assertEqual(scene, clone)
