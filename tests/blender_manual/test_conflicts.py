"""
Tests for conflicting operations that are sensitive to network timings,
for instance rename a collection on one side and add to collection on the other side.

Such conflits need a server with throttling control to reproduce the problem reliably.

So far, the tests cannot really be automated on CI/CD since they require lengthy wait
until all the messages are flushed and processed at the end before grabbing
the messages from all Blender
"""
from pathlib import Path
import unittest
import time

from parameterized import parameterized_class

from mixer.broadcaster.common import MessageType

import tests.blender_manual.blender_snippets as bl
from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class ThrottledTestCase(BlenderTestCase):
    def setUp(self, startup_file: str = "file1.blend"):
        try:
            files_folder = Path(__file__).parent / "files"
            file = files_folder / startup_file
            blenderdesc = BlenderDesc(load_file=file)
            blenderdescs = [blenderdesc, BlenderDesc()]

            self.latency = 1
            latency_ms = 1000 * self.latency
            server_args = ["--latency", str(latency_ms)]
            super().setUp(blenderdescs=blenderdescs, server_args=server_args, join=False)
            for blender in self._blenders:
                blender.connect_and_join_mixer(experimental_sync=self.experimental_sync)
                # if the second join is too early it is rejected with error "room not joinable yet"
                # if the test runs too early if may run before join is complete
                time.sleep(3.0)
        except Exception:
            self.shutdown()
            raise

    def assert_matches(self):
        # Wait for the messages to reach the destination
        # TODO What os just enough ?
        time.sleep(3 * self.latency)
        super().assert_matches()


@parameterized_class(
    [{"experimental_sync": True}, {"experimental_sync": False}], class_name_func=ThrottledTestCase.get_class_name,
)
class TestSimultaneousCreate(ThrottledTestCase):
    def test_object_in_master_collection(self):
        location = "0.0, -3.0, 0.0"
        self.send_strings([bl.active_layer_master_collection() + bl.ops_objects_light_add(location=location)], to=0)

        # with a delay > latency all the messages are transmitted and the problem does not occur
        # delay = 2.0

        time.sleep(0.0)

        location = "0.0, 3.0, 0.0"
        self.send_strings([bl.active_layer_master_collection() + bl.ops_objects_light_add(location=location)], to=1)

        if not self.experimental_sync:
            self.expected_counts = {MessageType.LIGHT: 2}
        self.assert_matches()
        pass


class TestCollectionInMasterRename(ThrottledTestCase):
    def test_add_object(self):
        self.send_strings([bl.active_layer_collection("Collection1"), bl.ops_objects_light_add()], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=1)

        # 2020-08-13 21:24:20,703 W mixer.blender_client                  -     collection = share_data.blender_collections[collection_name]                 [.\mixer\log_utils.py:62]
        # 2020-08-13 21:24:20,706 W mixer.blender_client                  - KeyError: 'Collection1'                                                         [.\mixer\log_utils.py:62]
        # The point light is in no collection
        successful = False
        self.assertTrue(successful)

    def test_unlink_object(self):
        self.send_strings([bl.collection_objects_unlink("EmptyInCollection1", "Collection1")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=1)

        # 2020-08-13 21:24:20,703 W mixer.blender_client                  -     collection = share_data.blender_collections[collection_name]                 [.\mixer\log_utils.py:62]
        # 2020-08-13 21:24:20,706 W mixer.blender_client                  - KeyError: 'Collection1'                                                         [.\mixer\log_utils.py:62]
        # The object is not removed
        successful = False
        self.assertTrue(successful)

    def test_data_collections_rename_same_name(self):
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=1)

        # exceptions
        successful = False
        self.assertTrue(successful)
        pass

    def test_data_collections_rename_different_names(self):
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed2")], to=1)

        # fails: collection is duplicated
        successful = False
        self.assertTrue(successful)

    def test_remove_collection(self):
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings(bl.data_collections_remove("Collection1"), to=1)

        # No problem
        successful = True
        self.assertTrue(successful)

    def test_remove_child(self):
        self.send_strings([bl.data_collections_rename("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_collections_remove("Collection11")], to=1)

        # Exception, scene OK
        successful = False
        self.assertTrue(successful)


class TestObjectRename(ThrottledTestCase):
    def test_update_object(self):
        self.send_strings([bl.data_objects_rename("A", "B")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_objects_update("B", ".location[1] = 2.")], to=1)

        # wrong object updated
        successful = False
        self.assertTrue(successful)


@parameterized_class(
    [{"experimental_sync": True}, {"experimental_sync": False}], class_name_func=ThrottledTestCase.get_class_name,
)
class TestSceneRename(ThrottledTestCase):
    def setUp(self):
        super().setUp("empty.blend")

    @unittest.skip("")
    def test_add_object(self):
        self.send_strings([bl.active_layer_master_collection(), bl.ops_objects_light_add()], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)

        # on 1 The light is in the scene but not in the master collection of the renamed scene
        successful = False
        self.assertTrue(successful)

    def test_add_collection(self):
        self.send_strings(
            [bl.data_collections_new("new_collection"), bl.scene_collection_children_link("new_collection"),], to=0,
        )
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)
        self.send_strings([bl.trigger_scene_update("Scene_renamed")], to=1)

        # on 1
        # - Scene and SceneRenames are present
        # - data_collections_new is linked to Scene_renamed instead of Scene
        if not self.experimental_sync:
            self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 1}
        self.assert_matches()

    @unittest.skip("")
    def test_data_objects_rename(self):
        self.send_strings([bl.data_objects_rename("EmptyInSceneMaster", "EmptyInSceneMaster_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)

        successful = True
        self.assertTrue(successful)

    @unittest.skip("")
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
        successful = False
        self.assertTrue(successful)

    @unittest.skip("")
    def test_unlink_collection(self):
        self.send_strings([bl.scene_collection_children_unlink("Collection1")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([bl.data_scenes_rename("Scene", "Scene_renamed")], to=1)

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
        successful = False
        self.assertTrue(successful)


if __name__ == "__main__":
    unittest.main()
