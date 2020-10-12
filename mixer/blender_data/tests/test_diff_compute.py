from pathlib import Path

import unittest

import bpy

from mixer.blender_data.bpy_data_proxy import BpyDataProxy
from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy
from mixer.blender_data.datablock_collection_proxy import DatablockRefCollectionProxy
from mixer.blender_data.proxy import DeltaAddition, DeltaDeletion, DeltaUpdate
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.struct_collection_proxy import StructCollectionProxy
from mixer.blender_data.struct_proxy import StructProxy

from mixer.blender_data.filter import test_properties


class DifferentialCompute(unittest.TestCase):
    def setUp(self):
        this_folder = Path(__file__).parent
        test_blend_file = str(this_folder / "empty.blend")
        file = test_blend_file
        bpy.ops.wm.open_mainfile(filepath=file)
        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.scene_proxy: DatablockProxy = self.proxy.data("scenes").search_one("Scene")
        self.scene = bpy.data.scenes["Scene"]
        self.scenes_property = bpy.data.bl_rna.properties["scenes"]

    def generate_all_uuids(self):
        # as a side effect, BpyBlendDiff generates the uuids
        _ = BpyBlendDiff()
        _.diff(self.proxy, test_properties)


class Datablock(DifferentialCompute):
    def test_datablock_builtin(self):
        # test_diff_compute.Datablock.test_datablock_builtin
        expected_float = 0.5
        self.scene.audio_volume = expected_float
        diff = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())

        # there is a pending issue with use_curve_mapping. it is filtered on proxy load, but not during diff
        # and is sone struct it has a value despite use_curve_mapping = False
        # TODO do not use curve_mapping. We wand the documents to be as close as possible
        # self.assertSetEqual(set(diff.value._data.keys()), {"audio_volume"})

        delta = diff.value._data["audio_volume"]
        self.assertIsInstance(delta, DeltaUpdate)
        value = delta.value
        self.assertIsInstance(value, float)
        self.assertEqual(value, expected_float)

    def test_datablock_struct_builtin(self):
        expected_bool = not self.scene.eevee.use_bloom
        self.scene.eevee.use_bloom = expected_bool
        diff = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())

        # there is a pending issue with use_curve_mapping. it is filtered on proxy load, but not during diff
        # and is sone struct it has a value despite use_curve_mapping = False
        # TODO do not use curve_mapping. We wand the documents to be as close as possible
        # self.assertSetEqual(set(diff.value._data.keys()), {"eevee"})

        delta_eevee = diff.value._data["eevee"]
        self.assertIsInstance(delta_eevee, DeltaUpdate)
        self.assertIsInstance(delta_eevee.value, StructProxy)
        self.assertSetEqual(set(delta_eevee.value._data.keys()), {"use_bloom"})
        delta_use_bloom = delta_eevee.value._data["use_bloom"]
        self.assertEqual(delta_use_bloom.value, expected_bool)


class StructDatablockRef(DifferentialCompute):
    # datablock reference in a struct
    # Scene.world
    def test_add(self):
        # set reference from NOne to a valid datablock
        # test_diff_compute.StructDatablockRef.test_add
        self.scene.world = None
        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        world = bpy.data.worlds.new("W")
        self.scene.world = world
        self.generate_all_uuids()
        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())
        self.assertIsInstance(scene_delta, DeltaUpdate)
        world_delta = scene_delta.value.data("world", resolve_delta=False)
        self.assertIsInstance(world_delta, DeltaUpdate)
        world_update = world_delta.value
        self.assertIsInstance(world_update, DatablockRefProxy)
        self.assertEqual(world_update._datablock_uuid, world.mixer_uuid)

    def test_update(self):
        # set reference from None to a valid datablock
        # test_diff_compute.StructDatablockRef.test_update
        world1 = bpy.data.worlds.new("W1")
        world2 = bpy.data.worlds.new("W2")
        self.scene.world = world1
        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.scene.world = world2
        self.generate_all_uuids()
        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())
        self.assertIsInstance(scene_delta, DeltaUpdate)
        world_delta = scene_delta.value.data("world", resolve_delta=False)
        self.assertIsInstance(world_delta, DeltaUpdate)
        world_update = world_delta.value
        self.assertIsInstance(world_update, DatablockRefProxy)
        self.assertEqual(world_update._datablock_uuid, world2.mixer_uuid)

    @unittest.skip("Need BpyIDRefNoneProxy")
    def test_remove(self):
        # set reference from a valid datablock to None
        # test_diff_compute.StructDatablockRef.test_remove
        world1 = bpy.data.worlds.new("W1")
        self.scene.world = world1
        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.scene.world = None
        self.generate_all_uuids()
        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())
        # TODO fails. should a null ref be implemented as a DatablockRefProxy
        # with a null ref (uuid is None)
        # or what else
        self.assertIsInstance(scene_delta, DeltaUpdate)
        world_delta = scene_delta.value.data("world")
        self.assertIsInstance(world_delta, DeltaDeletion)


class Collection(DifferentialCompute):
    # test_diff_compute.Collection

    # @unittest.skip("AttributeError: 'CollectionObjects' object has no attribute 'fixed_type'")
    def test_datablock_collection(self):
        # Scene.collection.objects
        # A collection of references to standalone datablocks

        # test_diff_compute.Collection.test_datablock_collection
        for i in range(2):
            name = f"Unchanged{i}"
            empty = bpy.data.objects.new(name, None)
            self.scene.collection.objects.link(empty)
        for i in range(2):
            name = f"Deleted{i}"
            empty = bpy.data.objects.new(name, None)
            self.scene.collection.objects.link(empty)

        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.scene_proxy = self.proxy.data("scenes").search_one("Scene")
        self.scene = bpy.data.scenes["Scene"]
        for i in range(2):
            name = f"Added{i}"
            empty = bpy.data.objects.new(name, None)
            self.scene.collection.objects.link(empty)
        for i in range(2):
            bpy.data.objects.remove(bpy.data.objects[f"Deleted{i}"])

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())

        self.assertIsInstance(scene_delta, DeltaUpdate)
        scene_update = scene_delta.value
        self.assertIsInstance(scene_update, DatablockProxy)
        self.assertTrue(scene_update.is_standalone_datablock)

        collection_delta = scene_update.data("collection", resolve_delta=False)
        self.assertIsInstance(scene_delta, DeltaUpdate)
        collection_update = collection_delta.value
        self.assertIsInstance(collection_update, DatablockProxy)
        self.assertTrue(collection_update.is_embedded_data)

        objects_delta = collection_update.data("objects", resolve_delta=False)
        self.assertIsInstance(objects_delta, DeltaUpdate)
        objects_update = objects_delta.value
        self.assertIsInstance(objects_update, DatablockRefCollectionProxy)

        deltas = {delta.value._initial_name: delta for delta in objects_update._data.values()}
        proxies = {name: delta.value for name, delta in deltas.items()}
        for name in ("Added0", "Added1"):
            self.assertIsInstance(deltas[name], DeltaAddition)
            self.assertIsInstance(proxies[name], DatablockRefProxy)

        for name in ("Deleted0", "Deleted1"):
            self.assertIsInstance(deltas[name], DeltaDeletion)
            self.assertIsInstance(proxies[name], DatablockRefProxy)

    def test_bpy_collection(self):
        # bpy.data.collections[x].objects
        # A collection of references to standalone datablocks

        # test_diff_compute.Collection.test_bpy_collection
        collection = bpy.data.collections.new("Collection")
        for i in range(2):
            empty = bpy.data.objects.new(f"Unchanged{i}", None)
            collection.objects.link(empty)
        for i in range(2):
            empty = bpy.data.objects.new(f"Unlinked{i}", None)
            collection.objects.link(empty)
        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.collection_proxy = self.proxy.data("collections").search_one("Collection")
        self.collection = bpy.data.collections["Collection"]
        for i in range(2):
            empty = bpy.data.objects.new(f"Added{i}", None)
            collection.objects.link(empty)
        for i in range(2):
            collection.objects.unlink(bpy.data.objects[f"Unlinked{i}"])

        self.generate_all_uuids()
        collections_property = bpy.data.bl_rna.properties["scenes"]

        collection_delta = self.collection_proxy.diff(self.collection, collections_property, self.proxy.context())

        self.assertIsInstance(collection_delta, DeltaUpdate)
        collection_update = collection_delta.value
        self.assertIsInstance(collection_update, DatablockProxy)
        self.assertTrue(collection_update.is_standalone_datablock)

        objects_delta = collection_update.data("objects", resolve_delta=False)
        self.assertIsInstance(objects_delta, DeltaUpdate)
        objects_update = objects_delta.value
        self.assertIsInstance(objects_update, DatablockRefCollectionProxy)

        #  test_diff_compute.Collection.test_bpy_collection
        deltas = {delta.value._initial_name: delta for delta in objects_update._data.values()}
        proxies = {name: delta.value for name, delta in deltas.items()}
        for name in ("Added0", "Added1"):
            self.assertIsInstance(deltas[name], DeltaAddition)
            self.assertIsInstance(proxies[name], DatablockRefProxy)

        for name in ("Unlinked0", "Unlinked1"):
            self.assertIsInstance(deltas[name], DeltaDeletion)
            self.assertIsInstance(proxies[name], DatablockRefProxy)

    def test_key_str(self):
        # Scene.render.views
        # A bpy_prop_collection with string keys

        # test_diff_compute.Collection.test_key_str

        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.scene_proxy = self.proxy.data("scenes").search_one("Scene")
        self.scene = bpy.data.scenes["Scene"]

        view = self.scene.render.views["right"]
        self.scene.render.views.remove(view)

        view = self.scene.render.views.new("New")

        view = self.scene.render.views["left"]
        view.file_suffix = "new_suffix"

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())

        self.assertIsInstance(scene_delta, DeltaUpdate)
        scene_update = scene_delta.value
        self.assertIsInstance(scene_update, DatablockProxy)
        self.assertTrue(scene_update.is_standalone_datablock)

        render_delta = scene_update.data("render", resolve_delta=False)
        self.assertIsInstance(render_delta, DeltaUpdate)
        render_update = render_delta.value
        self.assertIsInstance(render_update, StructProxy)

        views_delta = render_update.data("views", resolve_delta=False)
        self.assertIsInstance(views_delta, DeltaUpdate)
        views_update = views_delta.value
        self.assertIsInstance(views_update, StructCollectionProxy)

        # for why "A" and "D" see BpyProStructCollectionProxy.diff()
        self.assertIn("ANew", views_update)
        view_delta = views_update.data("ANew", resolve_delta=False)
        self.assertIsInstance(view_delta, DeltaAddition)
        view_update = view_delta.value
        self.assertIsInstance(view_update, StructProxy)

        self.assertIn("Dright", views_update)
        view_delta = views_update.data("Dright", resolve_delta=False)
        self.assertIsInstance(view_delta, DeltaDeletion)

        self.assertIn("left", views_update)
        view_delta = views_update.data("left", resolve_delta=False)
        self.assertIsInstance(view_delta, DeltaUpdate)
        view_update = view_delta.value
        self.assertIsInstance(view_update, StructProxy)
        property_delta = view_update.data("file_suffix", resolve_delta=False)
        self.assertIsInstance(view_delta, DeltaUpdate)
        self.assertEqual(property_delta.value, "new_suffix")

    def test_key_int(self):
        # Scene.view_settings.curve_mapping.curves
        # A bpy_prop_collection with string keys

        # test_diff_compute.Collection.test_key_int
        self.scene.view_settings.use_curve_mapping = True
        points_remove = self.scene.view_settings.curve_mapping.curves[0].points
        points_remove.new(0.5, 0.5)
        points_add = self.scene.view_settings.curve_mapping.curves[1].points

        self.proxy = BpyDataProxy()
        self.proxy.load(test_properties)
        self.scene_proxy = self.proxy.data("scenes").search_one("Scene")
        self.scene = bpy.data.scenes["Scene"]

        points_remove.remove(points_remove[1])
        points_add.new(2.0, 2.0)

        self.generate_all_uuids()

        scene_delta = self.scene_proxy.diff(self.scene, self.scenes_property, self.proxy.context())

        points_remove_proxy = (
            scene_delta.value.data("view_settings").data("curve_mapping").data("curves").data(0).data("points")
        )
        self.assertIsInstance(points_remove_proxy, StructCollectionProxy)

        # points are ordered by location. removing the second one produces an update
        # at index 1 and a delete at index 2
        point1 = points_remove_proxy.data(1)
        point1_update = point1.data("location", resolve_delta=False)
        self.assertIsInstance(point1_update, DeltaUpdate)
        location1 = point1_update.value
        self.assertAlmostEqual(location1[0], 1.0)
        self.assertAlmostEqual(location1[1], 1.0)

        point2 = points_remove_proxy.data(2, resolve_delta=False)
        self.assertIsInstance(point2, DeltaDeletion)

        points_add_proxy = (
            scene_delta.value.data("view_settings").data("curve_mapping").data("curves").data(1).data("points")
        )
        self.assertIsInstance(points_add_proxy, StructCollectionProxy)

        self.assertIsInstance(points_add_proxy.data(2, resolve_delta=False), DeltaAddition)

        # points are ordered by location. removing the second one produces an update
        # at index 1 and a delete at index 2
        point = points_add_proxy.data(2)
        location = point.data("location")
        self.assertAlmostEqual(location[0], 2.0)
        self.assertAlmostEqual(location[1], 2.0)
