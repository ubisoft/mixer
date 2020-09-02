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


class DifferentialApply(unittest.TestCase):
    def setUp(self):
        this_folder = Path(__file__).parent
        test_blend_file = str(this_folder / "empty.blend")
        file = test_blend_file
        bpy.ops.wm.open_mainfile(filepath=file)
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy: BpyIDProxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]
        self.scenes_property = bpy.data.bl_rna.properties["scenes"]

    def generate_all_uuids(self):
        # as a side effect, BpyBlendDiff generates the uuids
        _ = BpyBlendDiff()
        _.diff(self.proxy, test_context)


class Datablock(DifferentialApply):
    def test_builtin(self):
        # a python builtin in a dataclock
        # Scene.audio_volume

        # test_diff_apply.Datablock.test_builtin

        self.scene.audio_volume = 0.5
        delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # the diff has audio_volume, updated to 0.5

        # rollback to anything else
        self.scene.audio_volume = 0.0

        # apply the diff
        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, delta, self.proxy.visit_state())
        self.assertEqual(self.scene.audio_volume, 0.5)

    def test_struct_builtin(self):
        # a python builtin a a struct inside a datablock
        # Scene.eevee.use_bloom

        # test_diff_apply.Datablock.test_struct_builtin

        self.scene.eevee.use_bloom = False
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy: BpyIDProxy = self.proxy.data("scenes").data("Scene")
        self.scene.eevee.use_bloom = True

        delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # diff is -> True

        # reset
        self.scene.eevee.use_bloom = False

        # apply the diff
        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, delta, self.proxy.visit_state())
        self.assertEqual(self.scene.eevee.use_bloom, True)


class StructDatablockRef(DifferentialApply):
    # datablock reference in a struct
    # Scene.world

    @unittest.skip("Need BpyIDRefNoneProxy")
    def test_add(self):
        # set reference from None to a valid datablock
        # test_diff_apply.StructDatablockRef.test_add

        # TODO needs a BpyIDNoneRefProxy
        self.scene.world = None
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy: BpyIDProxy = self.proxy.data("scenes").data("Scene")

        world = bpy.data.worlds.new("W")
        self.scene.world = world
        self.generate_all_uuids()
        delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # diff -> set world

        # reset
        self.scene.world = None

        # apply the diff
        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, delta, self.proxy.visit_state())
        self.assertEqual(self.scene.eevee.use_bloom, True)

    def test_update(self):
        # set reference from None to a valid datablock
        # test_diff_apply.StructDatablockRef.test_update
        world1 = bpy.data.worlds.new("W1")
        world2 = bpy.data.worlds.new("W2")
        self.scene.world = world1
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy: BpyIDProxy = self.proxy.data("scenes").data("Scene")

        self.scene.world = world2
        self.generate_all_uuids()
        delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # diff -> world2

        # reset
        self.scene.world = world1

        # apply the diff
        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, delta, self.proxy.visit_state())
        self.assertEqual(self.scene.world, world2)

    @unittest.skip("Need BpyIDRefNoneProxy")
    def test_remove(self):
        # set reference from a valid datablock to None
        # test_diff_apply.StructDatablockRef.test_remove
        world1 = bpy.data.worlds.new("W1")
        self.scene.world = world1
        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene.world = None
        self.generate_all_uuids()
        delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # delta - > None


class Collection(DifferentialApply):
    # test_differential.Collection

    def test_datablock_collection(self):
        # Scene.collection.objects
        # A collection of references to standalone datablocks
        # tests BpyPropDataCollectionProxy.apply()

        # test_diff_apply.Collection.test_datablock_collection
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
            empty = bpy.data.objects[f"Deleted{i}"]
            self.scene.collection.objects.unlink(empty)

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # delta contains(deleted1, deleted 2, added1, added2)

        # reset
        for i in range(2):
            empty = bpy.data.objects[f"Deleted{i}"]
            self.scene.collection.objects.link(empty)
        for i in range(2):
            empty = bpy.data.objects[f"Added{i}"]
            self.scene.collection.objects.unlink(empty)

        # required because the Added{i} were created after proxy load and are not known by the proxy
        # at this time. IRL the depsgraph handler uses BpyBendDiff to find datablock additions,
        # then BpyBlendProxy.update()
        self.proxy.load(test_context)

        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, scene_delta, self.proxy.visit_state())

        self.assertIn("Unchanged0", self.scene.collection.objects)
        self.assertIn("Unchanged1", self.scene.collection.objects)
        self.assertIn("Added0", self.scene.collection.objects)
        self.assertIn("Added1", self.scene.collection.objects)
        self.assertNotIn("Deleted0", self.scene.collection.objects)
        self.assertNotIn("Deleted1", self.scene.collection.objects)

    def test_key_str(self):
        # Scene.render.views
        # A bpy_prop_collection with string keys
        # tests BpyPropStructCollectionProxy.apply()

        # test_diff_apply.Collection.test_key_str

        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]

        view_right = self.scene.render.views["right"]
        self.scene.render.views.remove(view_right)

        view = self.scene.render.views.new("New")

        view = self.scene.render.views["left"]
        view_left_suffix_bak = view.file_suffix
        view.file_suffix = "new_suffix"

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())

        # reset to initial state
        views = bpy.data.scenes["Scene"].render.views
        view_right = views.new("right")

        views["left"].file_suffix = view_left_suffix_bak

        view_new = views["New"]
        views.remove(view_new)

        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, scene_delta, self.proxy.visit_state())
        self.assertIn("New", views)
        self.assertIn("left", views)
        self.assertEqual(views["left"].file_suffix, "new_suffix")
        self.assertNotIn("right", views)

    def test_key_int(self):
        # Scene.view_settings.curve_mapping.curves
        # A bpy_prop_collection with string keys

        # test_diff_apply.Collection.test_key_int
        self.scene.view_settings.use_curve_mapping = True

        points0 = self.scene.view_settings.curve_mapping.curves[0].points
        points0.new(0.5, 0.5)

        points1 = self.scene.view_settings.curve_mapping.curves[1].points

        self.proxy = BpyBlendProxy()
        self.proxy.load(test_context)
        self.scene_proxy = self.proxy.data("scenes").data("Scene")
        self.scene = bpy.data.scenes["Scene"]

        points0.remove(points0[1])
        points1.new(2.0, 2.0)

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.visit_state())
        # the delta contains :
        #   curves[0]: Deletion of element 1
        #   curves[1]: Addition of element 2

        # reset state
        points0.new(0.5, 0.5)
        points1.remove(points1[2])

        self.scene_proxy.apply(bpy.data.scenes, self.scene.name, scene_delta, self.proxy.visit_state())
        self.assertEqual(len(points0), 2)
        self.assertEqual(list(points0[0].location), [0.0, 0.0])
        self.assertEqual(list(points0[1].location), [1.0, 1.0])

        self.assertEqual(len(points1), 3)
        self.assertEqual(list(points1[0].location), [0.0, 0.0])
        self.assertEqual(list(points1[1].location), [1.0, 1.0])
        self.assertEqual(list(points1[2].location), [2.0, 2.0])
