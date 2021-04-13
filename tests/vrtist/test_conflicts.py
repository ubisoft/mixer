"""
Tests for conflicting operations that are sensitive to network timings,
for instance rename a collection on one side and add to collection on the other side.

Such conflits need a server with throttling control to reproduce the problem reliably.

"""
import time
import unittest

from parameterized import parameterized_class

from mixer.broadcaster.common import MessageType

from tests import files_folder
import tests.blender_snippets as bl
from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class ThrottledTestCase(BlenderTestCase):
    def setUp(self, startup_file: str = "file2.blend"):
        try:
            file = files_folder() / startup_file
            blenderdesc = BlenderDesc(load_file=file)
            blenderdescs = [blenderdesc, BlenderDesc()]

            self.latency = 1
            latency_ms = 1000 * self.latency
            server_args = ["--latency", str(latency_ms)]
            super().setUp(blenderdescs=blenderdescs, server_args=server_args)
        except Exception:
            self.shutdown()
            raise

    def assert_matches(self):
        # Wait for the messages to reach the destination
        # TODO What os just enough ?
        time.sleep(4 * self.latency)
        super().assert_matches()


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=ThrottledTestCase.get_class_name,
)
class TestSimultaneousCreate(ThrottledTestCase):
    def setUp(self):
        super().setUp("empty.blend")

    def test_empty_unlinked(self):
        empties = 2
        if self.vrtist_protocol:
            self.expected_counts = {MessageType.TRANSFORM: empties}
            raise unittest.SkipTest("FAILS: Only one empty remains")
        else:
            scenes = 1
            self.expected_counts = {MessageType.BLENDER_DATA_CREATE: empties + scenes}

        create_empty = bl.data_objects_new("Empty", None)
        self.send_strings([create_empty], to=0)
        time.sleep(0.0)
        self.send_strings([create_empty], to=1)

        self.assert_matches()
        pass

    def test_empty_unlinked_many(self):
        empties = 2 * 5
        if self.vrtist_protocol:
            self.expected_counts = {MessageType.TRANSFORM: empties}
            raise unittest.SkipTest("FAILS: Only half of empties remains")
        else:
            scenes = 1
            self.expected_counts = {MessageType.BLENDER_DATA_CREATE: empties + scenes}

        create_empty = bl.data_objects_new("Empty", None)
        create_empties = [create_empty] * 5
        self.send_strings(create_empties, to=0)
        time.sleep(0.0)
        self.send_strings(create_empties, to=1)

        self.assert_matches()
        pass

    def test_object_in_master_collection(self):
        lights = 2
        if self.vrtist_protocol:
            self.expected_counts = {MessageType.LIGHT: lights}
            raise unittest.SkipTest("FAILS: Only one point light remains")

        command = """
import bpy
viewlayer = bpy.data.scenes["Scene"].view_layers["View Layer"]
viewlayer.active_layer_collection = viewlayer.layer_collection
bpy.ops.object.light_add(type="POINT", location=({location}))
"""

        command_0 = command.format(location="0.0, -3.0, 0.0")
        self.send_string(command_0, to=0)

        # with a delay > latency all the messages are transmitted and the problem does not occur
        # delay = 2.0

        time.sleep(0.0)

        command_1 = command.format(location="0.0, 3.0, 0.0")
        self.send_string(command_1, to=1)

        self.assert_matches()

        # Issue #222
        pass


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=ThrottledTestCase.get_class_name,
)
class TestCollectionInMasterRename(ThrottledTestCase):
    def setUp(self):
        if self.vrtist_protocol:
            self.skipTest("Fails in VRtist")
        super().setUp()

        # work around the ADD_OBJECT_TO_VRTIST mismatch that is caused because the message generation depends on the
        # active scene. So leave only one scene
        cleanup_scenes = """
import bpy
bpy.data.scenes.remove(bpy.data.scenes["Scene.001"])
"""
        self.send_string(cleanup_scenes, to=0)

    def send_string(self, s: str, to: int, sleep=0):
        super().send_string(s, to=to, sleep=sleep)

    def test_add_object(self):
        add_object = """\
import bpy
light = bpy.data.lights.new(name="point", type="POINT")
obj = bpy.data.objects.new("point", light)
bpy.data.collections["Collection1"].objects.link(obj)
"""
        rename = """\
import bpy
bpy.data.collections["Collection1"].name = "C1_renamed"
"""

        self.send_string(add_object, to=0)
        self.send_string(rename, to=1)

        self.assert_matches()

    def test_unlink_object(self):
        unlink = """\
import bpy
obj = bpy.data.objects["EmptyInCollection1"]
bpy.data.collections["Collection1"].objects.unlink(obj)
"""
        rename = """\
import bpy
bpy.data.collections["Collection1"].name = "Collection1_renamed"
"""
        self.send_string(unlink, to=0)
        self.send_string(rename, to=1)

        # 2020-08-13 21:24:20,703 W mixer.blender_client                  -     collection = share_data.blender_collections[collection_name]                 [.\mixer\log_utils.py:62]
        # 2020-08-13 21:24:20,706 W mixer.blender_client                  - KeyError: 'Collection1'                                                         [.\mixer\log_utils.py:62]
        # The object is not removed
        self.assert_matches()

    def test_data_collections_rename_same_name(self):
        rename = """\
import bpy
bpy.data.collections["Collection1"].name = "Collection1_renamed"
"""
        self.send_string(rename, to=0)
        self.send_string(rename, to=1)

        self.assert_matches()

    def test_data_collections_rename_different_names(self):
        rename = """\
import bpy
bpy.data.collections["Collection1"].name = "Collection1_renamed"
"""
        rename2 = """\
import bpy
bpy.data.collections["Collection1"].name = "Collection1_renamed2"
"""
        self.send_string(rename, to=0)
        self.send_string(rename2, to=1)

        # fails: collection has different names
        self.assert_matches()

    def test_remove_collection(self):
        rename = """\
import bpy
bpy.data.collections["Collection1"].name = "Collection1_renamed"
"""
        remove = """
import bpy
collection = bpy.data.collections["Collection1"]
bpy.data.collections.remove(collection)
"""

        self.send_string(rename, to=0)
        self.send_string(remove, to=1)

        # No problem
        self.assert_matches()

    def test_remove_child(self):
        remove = """
import bpy
collection = bpy.data.collections["Collection1"]
bpy.data.collections.remove(collection)
"""
        self.send_string(remove, to=0)
        delay = 0.0
        time.sleep(delay)
        remove_child = """
import bpy
collection = bpy.data.collections["Collection11"]
bpy.data.collections.remove(collection)
"""
        self.send_string(remove_child, to=1)

        # Exception, scene OK
        self.assert_matches()


class TestObjectRenameGeneric(ThrottledTestCase):
    def setUp(self):
        super().setUp("file2.blend")

        # work around the ADD_OBJECT_TO_VRTIST mismatch that is caused because the message generation depends on the
        # active scene. So leave only one scene
        cleanup_scenes = """
import bpy
bpy.data.scenes.remove(bpy.data.scenes["Scene.001"])
"""
        self.send_string(cleanup_scenes, to=0)

    def test_update_object(self):
        rename = """
import bpy
bpy.data.objects["A"].name = "B"
"""
        self.send_string(rename, to=0)
        delay = 0.0
        time.sleep(delay)
        update = """
import bpy
bpy.data.objects["B"].location[1] = 2.
"""
        self.send_string(update, to=1)
        time.sleep(1.0)
        # wrong object updated
        self.assert_matches()


class TestSceneRenameGeneric(ThrottledTestCase):
    def setUp(self):
        super().setUp("file2.blend")

        # work around the ADD_OBJECT_TO_VRTIST mismatch that is caused because the message generation depends on the
        # active scene. So leave only one scene
        cleanup_scenes = """
import bpy
bpy.data.scenes.remove(bpy.data.scenes["Scene.001"])
"""
        self.send_string(cleanup_scenes, to=0)

    def test_add_object(self):
        self.send_strings([bl.active_layer_master_collection(), bl.ops_objects_light_add()], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)

        # on 1 The light is in the scene but not in the master collection of the renamed scene
        self.assert_matches()

    def test_collection_new_and_link(self):
        self.send_strings(
            [bl.data_collections_new("new_collection"), bl.scene_collection_children_link("new_collection")],
            to=0,
        )
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)
        self.send_strings([bl.trigger_scene_update("Scene_renamed")], to=1)

        # on 1
        # - Scene and SceneRenames are present
        # - data_collections_new is linked to Scene_renamed instead of Scene
        if self.vrtist_protocol:
            self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 2 + 1}
        self.assert_matches()

    # @unittest.skip("")
    def test_data_objects_rename(self):
        self.send_strings([bl.data_objects_rename("EmptyInSceneMaster", "EmptyInSceneMaster_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)

        self.assert_matches()

    # @unittest.skip("")
    def test_unlink_object(self):
        self.send_strings([bl.scene_collection_objects_unilink("EmptyInSceneMaster")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)

        # 2020-08-14 19:07:04,172 I mixer.blender_client.scene            - build_remove_object_from_scene Scene <- EmptyInSceneMaster                       [.\mixer\blender_client\scene.py:156]
        # 2020-08-14 19:07:04,176 D mixer.share_data                      - Updating blender_scenes                                                          [.\mixer\share_data.py:264]
        # 2020-08-14 19:07:04,181 W mixer.blender_client                  - Exception during processing of message MessageType.REMOVE_OBJECT_FROM_SCENE      [.\mixer\blender_client\__init__.py:847]
        # 2020-08-14 19:07:04,207 W mixer.blender_client                  - Traceback (most recent call last):                                               [.\mixer\log_utils.py:62]
        # 2020-08-14 19:07:04,209 W mixer.blender_client                  -   File "C:\Users\Philippe\AppData\Roaming\Blender Foundation\Blender\2.83\scripts\addons\mixer\blender_client\__init__.py", line 800, in network_consumer [.\mixer\log_utils.py:62]
        # 2020-08-14 19:07:04,214 W mixer.blender_client                  -     scene_api.build_remove_object_from_scene(command.data)                       [.\mixer\log_utils.py:62]
        # 2020-08-14 19:07:04,219 W mixer.blender_client                  -   File "C:\Users\Philippe\AppData\Roaming\Blender Foundation\Blender\2.83\scripts\addons\mixer\blender_client\scene.py", line 157, in build_remove_object_from_scene [.\mixer\log_utils.py:62]
        # 2020-08-14 19:07:04,223 W mixer.blender_client                  -     scene = share_data.blender_scenes[scene_name]                                [.\mixer\log_utils.py:62]
        # 2020-08-14 19:07:04,226 W mixer.blender_client                  - KeyError: 'Scene'                                                                [.\mixer\log_utils.py:62]

        # in 1 the object is not removed
        # successful = False
        # self.assertTrue(successful)
        self.assert_matches()

    def test_collection_unlink(self):
        self.send_strings([bl.scene_collection_children_unlink("Collection1")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)
        self.send_strings([bl.trigger_scene_update("Scene_renamed")], to=1)

        # 2020-08-14 19:15:43,081 I mixer.blender_client.scene            - build_remove_collection_from_scene Scene <- Collection1                          [.\mixer\blender_client\scene.py:110]
        # 2020-08-14 19:15:43,085 D mixer.share_data                      - Updating blender_scenes                                                          [.\mixer\share_data.py:264]
        # 2020-08-14 19:15:43,087 W mixer.blender_client                  - Exception during processing of message MessageType.REMOVE_COLLECTION_FROM_SCENE  [.\mixer\blender_client\__init__.py:847]
        # 2020-08-14 19:15:43,101 W mixer.blender_client                  - Traceback (most recent call last):                                               [.\mixer\log_utils.py:62]
        # 2020-08-14 19:15:43,106 W mixer.blender_client                  -   File "C:\Users\Philippe\AppData\Roaming\Blender Foundation\Blender\2.83\scripts\addons\mixer\blender_client\__init__.py", line 796, in network_consumer [.\mixer\log_utils.py:62]
        # 2020-08-14 19:15:43,109 W mixer.blender_client                  -     scene_api.build_remove_collection_from_scene(command.data)                   [.\mixer\log_utils.py:62]
        # 2020-08-14 19:15:43,113 W mixer.blender_client                  -   File "C:\Users\Philippe\AppData\Roaming\Blender Foundation\Blender\2.83\scripts\addons\mixer\blender_client\scene.py", line 111, in build_remove_collection_from_scene [.\mixer\log_utils.py:62]
        # 2020-08-14 19:15:43,119 W mixer.blender_client                  -     scene = share_data.blender_scenes[scene_name]                                [.\mixer\log_utils.py:62]
        # 2020-08-14 19:15:43,123 W mixer.blender_client                  - KeyError: 'Scene'                                                                [.\mixer\log_utils.py:62]

        # in 1 the collection is not unlinked
        if self.vrtist_protocol:
            self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 2 - 1}
        self.assert_matches()
