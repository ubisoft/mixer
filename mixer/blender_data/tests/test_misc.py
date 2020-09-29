# GPLv3 License
#
# Copyright (C) 2020 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import copy
import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.proxy import (
    BpyBlendProxy,
    BpyIDRefProxy,
    SoaElement,
)
from mixer.blender_data.tests.utils import test_blend_file

from mixer.blender_data.filter import (
    Context,
    TypeFilterOut,
    test_context,
    test_filter,
)


class TestLoadProxy(unittest.TestCase):
    def setUp(self):
        file = test_blend_file
        # file = r"D:\work\data\test_files\BlenderSS 2_82.blend"
        bpy.ops.wm.open_mainfile(filepath=file)
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)

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

        filter_stack = copy.copy(test_filter)
        filter_stack.append({T.Scene: TypeFilterOut(T.SceneEEVEE)})
        proxy = BpyBlendProxy()
        proxy.load(Context(filter_stack))
        blend_data_ = proxy._data
        scene_ = blend_data_["scenes"]._data["Scene_0"]._data
        self.assertFalse("eevee" in scene_)

    # @unittest.skip("")
    def test_scene(self):
        # test_misc.TestLoadProxy.test_scene
        scene = self.proxy._data["scenes"]._data["Scene_0"]._data
        # will vary slightly during tiune tuning of the default filter
        self.assertGreaterEqual(len(scene), 45)
        self.assertLessEqual(len(scene), 55)

        # objects = scene["objects"]._data
        # self.assertEqual(4, len(objects))

        # for o in objects.values():
        #     self.assertEqual(type(o), BpyIDRefProxy, o)

        # builtin attributes (floats)
        frame_properties = [name for name in scene.keys() if name.startswith("frame_")]
        self.assertEqual(7, len(frame_properties))

        # bpy_struct
        eevee = scene["eevee"]._data
        self.assertEqual(58, len(eevee))

        # Currently mot loaded
        # # PropertiesGroup
        # cycles_proxy = scene["view_layers"]._data["View Layer"]._data["cycles"]
        # self.assertIsInstance(cycles_proxy, BpyPropertyGroupProxy)
        # self.assertEqual(32, len(cycles_proxy._data))

        # # The master collection
        # master_collection = scene["collection"]
        # self.assertIsInstance(master_collection, BpyIDProxy)

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

    def test_camera_focus_object_idref(self):
        # test_misc.TestLoadProxy.test_camera_focus_object_idref
        cam = D.cameras["Camera_0"]
        cam.dof.focus_object = D.objects["Cube"]
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        # load into proxy
        cam_proxy = self.proxy.data("cameras").data("Camera_0")
        focus_object_proxy = cam_proxy.data("dof").data("focus_object")
        self.assertIsInstance(focus_object_proxy, BpyIDRefProxy)
        self.assertEqual(focus_object_proxy._datablock_uuid, D.objects["Cube"].mixer_uuid)

    def test_camera_focus_object_none(self):
        # test_misc.TestLoadProxy.test_camera_focus_object_none
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        # load into proxy
        cam_proxy = self.proxy.data("cameras").data("Camera_0")
        focus_object_proxy = cam_proxy.data("dof").data("focus_object")
        self.assertIs(focus_object_proxy, None)


class TestProperties(unittest.TestCase):
    def test_one(self):
        context = test_context
        camera = D.cameras[0]

        # for 2.83.4
        expected_names = {
            "name",
            "name_full",
            "is_embedded_data",
            "type",
            "sensor_fit",
            "passepartout_alpha",
            "angle_x",
            "angle_y",
            "angle",
            "clip_start",
            "clip_end",
            "lens",
            "sensor_width",
            "sensor_height",
            "ortho_scale",
            "display_size",
            "shift_x",
            "shift_y",
            "stereo",
            "show_limits",
            "show_mist",
            "show_passepartout",
            "show_safe_areas",
            "show_safe_center",
            "show_name",
            "show_sensor",
            "show_background_images",
            "lens_unit",
            "show_composition_center",
            "show_composition_center_diagonal",
            "show_composition_thirds",
            "show_composition_golden",
            "show_composition_golden_tria_a",
            "show_composition_golden_tria_b",
            "show_composition_harmony_tri_a",
            "show_composition_harmony_tri_b",
            "dof",
            "background_images",
            "animation_data",
            "cycles",
        }
        names = {prop[0] for prop in context.properties(camera)}
        self.assertSetEqual(names, expected_names, "Expected list from 2.83.4, check version")


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

    def test_derived_from_id(self):
        light = bpy.data.lights.new("new_area", "AREA")
        blenddata = BlendData.instance()
        collection_name = blenddata.bl_collection_name_from_ID(type(light))
        self.assertEqual(collection_name, "lights")


class TestAosSoa(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)

    def test_all_soa_grease_pencil(self):
        import array

        bpy.ops.object.gpencil_add(type="STROKE")
        proxy = BpyBlendProxy()
        proxy.load(test_context)
        gp_layers = proxy.data("grease_pencils").data("Stroke").data("layers")
        gp_points = gp_layers.data("Lines").data("frames").data(0).data("strokes").data(0).data("points")._data
        expected = (
            ("co", array.array, "f"),
            ("pressure", array.array, "f"),
            ("strength", array.array, "f"),
            ("uv_factor", array.array, "f"),
            ("uv_rotation", array.array, "f"),
            ("select", list, bool),
        )
        for name, type_, element_type in expected:
            self.assertIn("co", gp_points)
            item = gp_points[name]
            self.assertIsInstance(item, SoaElement)
            self.assertIsInstance(item._data, type_)
            if type_ is array.array:
                self.assertEqual(item._data.typecode, element_type)
            else:
                self.assertIsInstance(item._data[0], element_type)

        self.assertEqual(len(gp_points["pressure"]._data), len(gp_points["strength"]._data))
        self.assertEqual(3 * len(gp_points["pressure"]._data), len(gp_points["co"]._data))
