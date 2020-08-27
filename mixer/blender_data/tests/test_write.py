import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.proxy import BpyBlendProxy, BpyIDProxy, BpyIDRefProxy, write_attribute
from mixer.blender_data.tests.utils import register_bl_equals, test_blend_file

from mixer.blender_data.filter import test_context
from mathutils import Matrix, Vector

context = test_context


class TestWriteAttribute(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)

        # otherwise the loaded scene  way have curves despite use_curve_mapping==False and
        # the new one will not have curves and will not receive them as they are not send
        # use_curve_mapping == False
        D.scenes["Scene_0"].view_settings.use_curve_mapping = True

        self.proxy = BpyBlendProxy()
        self.proxy.load(context)
        register_bl_equals(self, context)

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
            write_attribute(bl_instance, name, value, self.proxy.visit_state())
            stored_value = getattr(bl_instance, name)
            stored_type = type(stored_value)
            self.assertEqual(stored_type(value), stored_value)

    def test_write_bpy_struct_scene_eevee(self):
        scene = D.scenes[0]
        eevee_proxy = self.proxy._data["scenes"]._data["Scene_0"]._data["eevee"]
        eevee_proxy._data["gi_cubemap_resolution"] = "64"
        eevee_proxy.save(scene, "eevee", self.proxy.visit_state())
        self.assertEqual("64", scene.eevee.gi_cubemap_resolution)

    def test_write_bpy_property_group_scene_cycles(self):
        # Not very useful it derives from struct
        scene = D.scenes[0]
        cycles_proxy = self.proxy._data["scenes"]._data["Scene_0"]._data["cycles"]
        cycles_proxy._data["shading_system"] = True
        cycles_proxy.save(scene, "cycles", self.proxy.visit_state())
        self.assertEqual(True, scene.cycles.shading_system)

    def test_write_array_of_struct_with_vec(self):
        # self.addTypeEqualityFunc(D.bpy_struct, bl_equalityfunc)
        cube = D.meshes["Cube"]
        vertices_proxy = self.proxy._data["meshes"]._data["Cube"]._data["vertices"]

        # loaded as SOA into array.array
        co_proxy = vertices_proxy._data["co"]._data

        # first vertex
        co_proxy[0] *= 2
        co_proxy[1] *= 2
        co_proxy[2] *= 2

        vertices_proxy.save(cube, "vertices", self.proxy.visit_state())
        self.assertListEqual(list(cube.vertices[0].co[0:3]), co_proxy[0:3].tolist())

    # explicit test per data type , including addition in collections

    def test_write_light(self):
        light_name = "Light"
        clone_name = f"Clone of {light_name}"
        light_proxy = self.proxy._data["lights"]._data[light_name]
        expected_energy = 666
        light_proxy._data["energy"] = expected_energy
        light_type = light_proxy._data["type"]
        light_proxy.rename(clone_name)
        clone_light = D.lights.new(clone_name, light_type)
        light_proxy.save()
        self.assertEqual(clone_light.energy, expected_energy)

    def test_write_world(self):
        # test_write.TestWriteAttribute.test_write_world
        world_name = "World"
        clone_name = f"Clone of {world_name}"
        world_clone = D.worlds.new(clone_name)
        world_proxy = self.proxy._data["worlds"]._data[world_name]
        world_proxy.rename(clone_name)
        world_proxy.save()
        self.assertEqual(world_clone, D.worlds[world_name])

    def test_write_array_curvemap(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)

        light_name = "Light"
        light = D.lights["Light"]
        points = [(0.111, 0.222), (0.333, 0.444)]
        curve0 = light.falloff_curve.curves[0]
        for i, point in enumerate(points):
            curve0.points[i].location = point

        self.proxy = BpyBlendProxy()
        self.proxy.load(context)
        clone_name = f"Clone of {light_name}"
        light_proxy = self.proxy._data["lights"]._data[light_name]
        light_type = light_proxy._data["type"]
        light_proxy.rename(clone_name)
        clone_light = D.lights.new(clone_name, light_type)
        light_proxy.save()
        clone_curve = clone_light.falloff_curve.curves[0]
        for i, point in enumerate(points):
            for clone, expected in zip(clone_curve.points[i].location, point):
                self.assertAlmostEqual(clone, expected)

    def test_shrink_array_curvemap(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)

        src_light_name = "Light"
        src_light = D.lights["Light"]
        src_points = [(0.666, 0.777), (0.888, 0.999)]
        curve0 = src_light.falloff_curve.curves[0]
        for i, point in enumerate(src_points):
            curve0.points[i].location = point

        self.proxy = BpyBlendProxy()
        self.proxy.load(context)
        light_proxy = self.proxy.data("lights").data(src_light_name)
        light_type = light_proxy.data("type")

        # Create a light then restore src_light into it
        dst_light_name = "Dst Light"
        dst_light = D.lights.new(dst_light_name, light_type)
        # extend the dst curvemap to 3 points
        dst_points = [(0.111, 0.222), (0.333, 0.444), (0.555, 0.666)]
        curve0 = dst_light.falloff_curve.curves[0]
        curve0.points.new(*dst_points[2])
        for i, point in enumerate(dst_points):
            curve0.points[i].location = point

        # patch the light name to restore the proxy into dst_light
        light_proxy.rename(dst_light_name)
        # save() needs to shrink the dst curvemap
        light_proxy.save(D.lights, dst_light_name)
        dst_curve = dst_light.falloff_curve.curves[0]
        self.assertEqual(len(src_points), len(dst_curve.points))
        for i, point in enumerate(src_points):
            for dst, expected in zip(dst_curve.points[i].location, point):
                self.assertAlmostEqual(dst, expected)

    def test_extend_array_curvemap(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)

        src_light_name = "Light"
        src_light = D.lights["Light"]
        # extend the source curvemap to 3 points
        src_points = [(0.111, 0.222), (0.333, 0.444), (0.555, 0.666)]
        curve0 = src_light.falloff_curve.curves[0]
        curve0.points.new(*src_points[2])
        for i, point in enumerate(src_points):
            curve0.points[i].location = point

        self.proxy = BpyBlendProxy()
        self.proxy.load(context)
        light_proxy = self.proxy.data("lights").data(src_light_name)
        light_type = light_proxy.data("type")

        # Create a light then restore src_light into it
        dst_light_name = "Dst Light"
        dst_light = D.lights.new(dst_light_name, light_type)
        # patch the light name to restore the proxy into dst_light
        light_proxy.rename(dst_light_name)
        # the dst curvemap has 2 points by default
        # save() needs to extend
        light_proxy.save(D.lights, dst_light_name)
        dst_curve = dst_light.falloff_curve.curves[0]
        self.assertEqual(len(src_points), len(dst_curve.points))
        for i, point in enumerate(src_points):
            for dst, expected in zip(dst_curve.points[i].location, point):
                self.assertAlmostEqual(dst, expected)

    def test_write_datablock_scene(self):
        # Write a whole scene datablock
        scene_name = "Scene_0"
        scene = D.scenes[scene_name]
        scene_proxy = self.proxy.data("scenes").data(scene_name)
        self.assertIsInstance(scene_proxy, BpyIDProxy)

        scene.name = "scene_bak"
        scene_bak = D.scenes["scene_bak"]

        scene_proxy.save(D.scenes, scene_name, self.proxy.visit_state())
        self.assertEqual(D.scenes[scene_name], scene_bak)

    def test_write_datablock_reference_scene_world(self):
        # just write the Scene.world attribute
        scene_name = "Scene_0"
        scene = D.scenes[scene_name]
        expected_world = scene.world
        assert expected_world is not None

        world_ref_proxy = self.proxy.data("scenes").data(scene_name).data("world")
        self.assertIsInstance(world_ref_proxy, BpyIDRefProxy)

        scene.world = None
        assert scene.world != expected_world

        world_ref_proxy.save(scene, "world", self.proxy.visit_state())
        self.assertEqual(scene.world, expected_world)

    def test_write_datablock_with_reference_camera_dof_target(self):
        # Write the whole camera datablock, including its reference to dof target

        camera_name = "Camera_0"
        camera = D.cameras[camera_name]

        # setup the scene and reload
        focus_object = D.objects["Cube"]
        camera.dof.focus_object = focus_object
        self.proxy = BpyBlendProxy()
        self.proxy.load(context)

        camera.name = "camera_bak"

        camera_proxy = self.proxy.data("cameras").data(camera_name)
        camera_proxy.save(D.cameras, camera_name, self.proxy.visit_state())
        self.assertEqual(D.cameras[camera_name].dof.focus_object, focus_object)
