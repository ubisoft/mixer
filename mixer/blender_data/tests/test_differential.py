from pathlib import Path

import unittest

import bpy

from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.proxy import (
    BpyBlendProxy,
    BpyIDProxy,
    BpyIDRefProxy,
    BpyPropDataCollectionProxy,
    BpyPropStructCollectionProxy,
    BpyStructProxy,
    DeltaAddition,
    DeltaDeletion,
    DeltaUpdate,
)

from mixer.blender_data.filter import test_context


class DifferentialCompute(unittest.TestCase):
    def setUp(self):
        this_folder = Path(__file__).parent
        test_blend_file = str(this_folder / "empty.blend")
        file = test_blend_file
        bpy.ops.wm.open_mainfile(filepath=file)
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]
        self.scenes_property = bpy.data.bl_rna.properties["scenes"]

    def generate_all_uuids(self):
        # as a side effect, BpyBlendDiff generates the uuids
        _ = BpyBlendDiff()
        _.diff(self.proxy, test_context)


class Datablock(DifferentialCompute):
    def test_datablock_builtin(self):
        # test_differential.Datablock.test_datablock_builtin
        expected_float = 0.5
        self.scene.audio_volume = expected_float
        diff = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        self.assertSetEqual(set(diff.value._data.keys()), {"audio_volume"})
        delta = diff.value._data["audio_volume"]
        self.assertIsInstance(delta, DeltaUpdate)
        value = delta.value
        self.assertIsInstance(value, float)
        self.assertEqual(value, expected_float)

    def test_datablock_struct_builtin(self):
        expected_bool = not self.scene.eevee.use_bloom
        self.scene.eevee.use_bloom = expected_bool
        diff = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        self.assertSetEqual(set(diff.value._data.keys()), {"eevee"})
        delta_eevee = diff.value._data["eevee"]
        self.assertIsInstance(delta_eevee, DeltaUpdate)
        self.assertIsInstance(delta_eevee.value, BpyStructProxy)
        self.assertSetEqual(set(delta_eevee.value._data.keys()), {"use_bloom"})
        delta_use_bloom = delta_eevee.value._data["use_bloom"]
        self.assertEqual(delta_use_bloom.value, expected_bool)


class StructDatablockRef(DifferentialCompute):
    # datablock reference in a struct
    # Scene.world
    def test_add(self):
        # set reference from NOne to a valid datablock
        # test_differential.StructDatablockRef.test_add
        self.scene.world = None
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        world = bpy.data.worlds.new("W")
        self.scene.world = world
        self.generate_all_uuids()
        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        self.assertIsInstance(scene_delta, DeltaUpdate)
        world_delta = scene_delta.value.data("world")
        self.assertIsInstance(world_delta, DeltaUpdate)
        world_update = world_delta.value
        self.assertIsInstance(world_update, BpyIDRefProxy)
        self.assertEqual(world_update._datablock_uuid, world.mixer_uuid)

    def test_update(self):
        # set reference from None to a valid datablock
        # test_differential.StructDatablockRef.test_update
        world1 = bpy.data.worlds.new("W1")
        world2 = bpy.data.worlds.new("W2")
        self.scene.world = world1
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene.world = world2
        self.generate_all_uuids()
        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        self.assertIsInstance(scene_delta, DeltaUpdate)
        world_delta = scene_delta.value.data("world")
        self.assertIsInstance(world_delta, DeltaUpdate)
        world_update = world_delta.value
        self.assertIsInstance(world_update, BpyIDRefProxy)
        self.assertEqual(world_update._datablock_uuid, world2.mixer_uuid)

    @unittest.skip("Need BpyIDRefNoneProxy")
    def test_remove(self):
        # set reference from a valid datablock to None
        # test_differential.StructDatablockRef.test_remove
        world1 = bpy.data.worlds.new("W1")
        self.scene.world = world1
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene.world = None
        self.generate_all_uuids()
        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # TODO fails. should a null ref be implemented as a BpyIDRefProxy
        # with a null ref (uuid is None)
        # or what else
        self.assertIsInstance(scene_delta, DeltaUpdate)
        world_delta = scene_delta.value.data("world")
        self.assertIsInstance(world_delta, DeltaDeletion)


class Collection(DifferentialCompute):
    # test_differential.Collection

    # @unittest.skip("AttributeError: 'CollectionObjects' object has no attribute 'fixed_type'")
    def test_datablock_collection(self):
        # Scene.collection.objects
        # A collection of references to standalone datablocks

        # test_differential.Collection.test_datablock_collection
        for i in range(2):
            empty = bpy.data.objects.new(f"Unchanged{i}", None)
            self.scene.collection.objects.link(empty)
        for i in range(2):
            empty = bpy.data.objects.new(f"Deleted{i}", None)
            self.scene.collection.objects.link(empty)
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]
        for i in range(2):
            empty = bpy.data.objects.new(f"Added{i}", None)
            self.scene.collection.objects.link(empty)
        for i in range(2):
            bpy.data.objects.remove(bpy.data.objects[f"Deleted{i}"])

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())

        self.assertIsInstance(scene_delta, DeltaUpdate)
        scene_update = scene_delta.value
        self.assertIsInstance(scene_update, BpyIDProxy)
        self.assertTrue(scene_update.is_standalone_datablock)

        collection_delta = scene_update.data("collection")
        self.assertIsInstance(scene_delta, DeltaUpdate)
        collection_update = collection_delta.value
        self.assertIsInstance(collection_update, BpyIDProxy)
        self.assertTrue(collection_update.is_embedded_data)

        objects_delta = collection_update.data("objects")
        self.assertIsInstance(objects_delta, DeltaUpdate)
        objects_update = objects_delta.value
        self.assertIsInstance(objects_update, BpyPropDataCollectionProxy)

        self.assertIn("Added0", objects_update)
        self.assertIn("Added1", objects_update)
        object_delta = objects_update.data("Added0")
        self.assertIsInstance(object_delta, DeltaAddition)
        object_update = object_delta.value
        self.assertIsInstance(object_update, BpyIDRefProxy)

        self.assertIn("Deleted0", objects_update)
        self.assertIn("Deleted1", objects_update)
        object_delta = objects_update.data("Deleted0")
        self.assertIsInstance(object_delta, DeltaDeletion)

    def test_key_str(self):
        # Scene.render.views
        # A bpy_prop_collection with string keys

        # test_differential.Collection.test_key_str

        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]

        view = self.scene.render.views["right"]
        self.scene.render.views.remove(view)

        view = self.scene.render.views.new("New")

        view = self.scene.render.views["left"]
        view.file_suffix = "new_suffix"

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())

        self.assertIsInstance(scene_delta, DeltaUpdate)
        scene_update = scene_delta.value
        self.assertIsInstance(scene_update, BpyIDProxy)
        self.assertTrue(scene_update.is_standalone_datablock)

        render_delta = scene_update.data("render")
        self.assertIsInstance(render_delta, DeltaUpdate)
        render_update = render_delta.value
        self.assertIsInstance(render_update, BpyStructProxy)

        views_delta = render_update.data("views")
        self.assertIsInstance(views_delta, DeltaUpdate)
        views_update = views_delta.value
        self.assertIsInstance(views_update, BpyPropStructCollectionProxy)

        self.assertIn("New", views_update)
        view_delta = views_update.data("New")
        self.assertIsInstance(view_delta, DeltaAddition)
        view_update = view_delta.value
        self.assertIsInstance(view_update, BpyStructProxy)

        self.assertIn("right", views_update)
        view_delta = views_update.data("right")
        self.assertIsInstance(view_delta, DeltaDeletion)

        self.assertIn("left", views_update)
        view_delta = views_update.data("left")
        self.assertIsInstance(view_delta, DeltaUpdate)
        view_update = view_delta.value
        self.assertIsInstance(view_update, BpyStructProxy)
        property_delta = view_update.data("file_suffix")
        self.assertIsInstance(view_delta, DeltaUpdate)
        self.assertEqual(property_delta.value, "new_suffix")

    def test_key_int(self):
        # Scene.view_settings.curve_mapping.curves
        # A bpy_prop_collection with string keys

        # test_differential.Collection.test_key_int
        self.scene.view_settings.use_curve_mapping = True
        points_remove = self.scene.view_settings.curve_mapping.curves[0].points
        points_remove.new(0.5, 0.5)
        points_add = self.scene.view_settings.curve_mapping.curves[1].points

        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]

        points_remove.remove(points_remove[1])
        points_add.new(2.0, 2.0)

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())

        points_remove_proxy = (
            scene_delta.value.data("view_settings")
            .value.data("curve_mapping")
            .value.data("curves")
            .value.data(0)
            .value.data("points")
            .value
        )
        self.assertIsInstance(points_remove_proxy, BpyPropStructCollectionProxy)

        # points are ordered by location. removing the second one produces an update
        # at index 1 and a delete at index 2
        point1 = points_remove_proxy.data(1).value
        point1_update = point1.data("location")
        self.assertIsInstance(point1_update, DeltaUpdate)
        location1 = point1_update.value
        self.assertAlmostEqual(location1[0], 1.0)
        self.assertAlmostEqual(location1[1], 1.0)

        point2 = points_remove_proxy.data(2)
        self.assertIsInstance(point2, DeltaDeletion)

        points_add_proxy = (
            scene_delta.value.data("view_settings")
            .value.data("curve_mapping")
            .value.data("curves")
            .value.data(1)
            .value.data("points")
            .value
        )
        self.assertIsInstance(points_add_proxy, BpyPropStructCollectionProxy)

        self.assertIsInstance(points_add_proxy.data(2), DeltaAddition)

        # points are ordered by location. removing the second one produces an update
        # at index 1 and a delete at index 2
        point = points_add_proxy.data(2).value
        location = point.data("location")
        self.assertAlmostEqual(location[0], 2.0)
        self.assertAlmostEqual(location[1], 2.0)
