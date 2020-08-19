"""
Tests for conflicting operations that are sensitive to network timings,
for instance rename a collection on one side and add to collection on the other side.

Such conflits need a server with throttling control to reprodure the problem reliably.

So far, the tests cannot really be automated on CI/CD since they require lengthy wait
untill all the messages are flished and processed at the end before grabbing
the messages from all Blender
"""
from pathlib import Path
import unittest
import time
from typing import List, Optional

from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class ThrottledTestCase(BlenderTestCase):
    def setUp(self):
        files_folder = Path(__file__).parent / "files"
        file = files_folder / "file1.blend"
        blenderdesc = BlenderDesc(load_file=file)
        blenderdescs = [blenderdesc, BlenderDesc()]

        latency_ms = 1000
        server_args = ["--latency", str(latency_ms)]
        super().setUp(blenderdescs=blenderdescs, server_args=server_args, join=False)
        for blender in self._blenders:
            blender.connect_and_join_mixer(experimental=self.experimental_sync)
            # if the second join is too early it is rejected with error "room not joinable yet"
            # if the test runs too early if may run before join is complete
            time.sleep(3.0)


def add_light(light_type: Optional[str] = "POINT", location: Optional[str] = "0.0, 0.0, 0.0") -> str:
    return f"""
import bpy
bpy.ops.object.light_add(type="{light_type}", location=({location}))
"""


def delete_object(name: str) -> str:
    return f"""
import bpy
object = bpy.data.objects["{name}"]
bpy.data.objects.remove(object)
"""


def new_data(collection_name: str, name: str) -> str:
    return f"""
import bpy
data = bpy.data.{collection_name}.new("{name}")
"""


def new_collection(name: str) -> str:
    return new_data("collections", name)


def rename_data(collection_name: str, old_name: str, new_name: str) -> str:
    return f"""
import bpy
bpy.data.{collection_name}["{old_name}"].name = "{new_name}"
"""


def rename_object(old_name: str, new_name: str) -> str:
    return rename_data("objects", old_name, new_name)


def select_collection(collection: str, scene: Optional[str] = "Scene", viewlayer: Optional[str] = "View Layer") -> str:
    return f"""
import bpy
viewlayer = bpy.data.scenes["{scene}"].view_layers["{viewlayer}"]
collection = viewlayer.layer_collection.children["{collection}"]
viewlayer.active_layer_collection = collection
"""


def select_master_collection(scene: Optional[str] = "Scene", viewlayer: Optional[str] = "View Layer") -> str:
    return f"""
import bpy
viewlayer = bpy.data.scenes["{scene}"].view_layers["{viewlayer}"]
viewlayer.active_layer_collection = viewlayer.layer_collection
"""


def rename_scene(old_name: str, new_name: str) -> str:
    return rename_data("scenes", old_name, new_name)


def rename_collection(old_name: str, new_name: str) -> str:
    return rename_data("collections", old_name, new_name)


def unlink_object_from_master_collection(object_name: str, scene_name: Optional[str] = "Scene") -> str:
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
object = bpy.data.objects["{object_name}"]
scene.collection.objects.unlink(object)
"""


def link_collection_to_master_collection(collection_name: str, scene_name: Optional[str] = "Scene") -> str:
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
collection = bpy.data.collections["{collection_name}"]
scene.collection.children.link(collection)
"""


def unlink_collection_from_master_collection(collection_name: str, scene_name: Optional[str] = "Scene") -> str:
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
collection = bpy.data.collections["{collection_name}"]
scene.collection.children.unlink(collection)
"""


def unlink_object_from_collection(object_name: str, collection_name: str) -> str:
    return f"""
import bpy
object = bpy.data.objects["{object_name}"]
collection = bpy.data.collections["{collection_name}"]
collection.objects.unlink(object)
"""


def remove_collection(collection_name: str) -> List[str]:
    return f"""
import bpy
collection = bpy.data.collections["{collection_name}"]
bpy.data.collections.remove(collection)
"""


class TestConflicts(ThrottledTestCase):
    def test_simultaneous_create(self):
        action = f"""
import bpy
bpy.ops.object.light_add(type='POINT', location=(0.0, -3.0, 0.0))
"""
        self.send_string(action, to=0)

        # with a delay > latency all the messages are transmitted and the problem does not occur
        # delay = 2.0

        time.sleep(2.0)

        action = f"""
import bpy
bpy.ops.object.light_add(type='POINT', location=(0.0, 3.0, 0.0))
"""
        self.send_string(action, to=1)

        pass


class TestCollectionInMasterRename(ThrottledTestCase):
    def test_add_object(self):
        self.send_strings([select_collection("Collection1"), add_light()], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=1)

        # 2020-08-13 21:24:20,703 W mixer.blender_client                  -     collection = share_data.blender_collections[collection_name]                 [.\mixer\log_utils.py:62]
        # 2020-08-13 21:24:20,706 W mixer.blender_client                  - KeyError: 'Collection1'                                                         [.\mixer\log_utils.py:62]
        # The point light is in no collection
        successful = False
        self.assertTrue(successful)

    def test_unlink_object(self):
        self.send_strings([unlink_object_from_collection("EmptyInCollection1", "Collection1")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=1)

        # 2020-08-13 21:24:20,703 W mixer.blender_client                  -     collection = share_data.blender_collections[collection_name]                 [.\mixer\log_utils.py:62]
        # 2020-08-13 21:24:20,706 W mixer.blender_client                  - KeyError: 'Collection1'                                                         [.\mixer\log_utils.py:62]
        # The object is not removed
        successful = False
        self.assertTrue(successful)

    def test_rename_collection_same_name(self):
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=1)

        # exceptions
        successful = False
        self.assertTrue(successful)
        pass

    def test_rename_collection_different_names(self):
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_collection("Collection1", "Collection1_renamed2")], to=1)

        # fails: collection is duplicated
        successful = False
        self.assertTrue(successful)

    def test_remove_collection(self):
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings(remove_collection("Collection1"), to=1)

        # No problem
        successful = True
        self.assertTrue(successful)

    def test_remove_child(self):
        self.send_strings([rename_collection("Collection1", "Collection1_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([remove_collection("Collection11")], to=1)

        # Exception, scene OK
        successful = False
        self.assertTrue(successful)


def update_object(name: str, property_update: str) -> str:
    return f"""
import bpy
bpy.data.objects["{name}"]{property_update}
"""


class TestObjectRename(ThrottledTestCase):
    def test_update_object(self):
        self.send_strings([rename_object("A", "B")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([update_object("B", ".location[1] = 2.")], to=1)

        # wrong object updated
        successful = False
        self.assertTrue(successful)


class TestSceneRename(ThrottledTestCase):
    def test_add_object(self):
        self.send_strings([select_master_collection(), add_light()], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_scene("Scene", "Scene_renamed")], to=1)

        # on 1 The light is in the scene but not in the master collection of the renamed scene
        successful = False
        self.assertTrue(successful)

    def test_add_collection(self):
        self.send_strings(
            [new_collection("new_collection"), link_collection_to_master_collection("new_collection")], to=0
        )
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_scene("Scene", "Scene_renamed")], to=1)

        # on 1
        # - Scene and SceneRenames are present
        # - new_collection is linked to Scene_renamed instead of Scene
        successful = False
        self.assertTrue(successful)

    def test_rename_object(self):
        self.send_strings([rename_object("EmptyInSceneMaster", "EmptyInSceneMaster_renamed")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_scene("Scene", "Scene_renamed")], to=1)

        successful = True
        self.assertTrue(successful)

    def test_unlink_object(self):
        self.send_strings([unlink_object_from_master_collection("EmptyInSceneMaster")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_scene("Scene", "Scene_renamed")], to=1)

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

    def test_unlink_collection(self):
        self.send_strings([unlink_collection_from_master_collection("Collection1")], to=0)
        delay = 0.0
        time.sleep(delay)
        self.send_strings([rename_scene("Scene", "Scene_renamed")], to=1)

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
