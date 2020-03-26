import unittest
import testcase
from pathlib import Path
import blender_lib as bl


class SceneTestCase(testcase.BlenderTestCase):
    def new_object(self, name: str):
        self._sender.send_function(bl.new_object, name)

    def new_collection(self, name: str):
        self._sender.send_function(bl.new_collection, name)

    def new_scene(self, name: str):
        self._sender.send_function(bl.new_scene, name)

    def remove_scene(self, name: str):
        self._sender.send_function(bl.remove_scene, name)

    def link_collection_to_scene(self, scene_name: str, collection_name: str):
        self._sender.send_function(bl.link_collection_to_scene, scene_name, collection_name)

    def unlink_collection_from_scene(self, scene_name: str, collection_name: str):
        self._sender.send_function(bl.unlink_collection_from_scene, scene_name, collection_name)

    def link_object_to_scene(self, scene_name: str, object_name: str):
        self._sender.send_function(bl.link_object_to_scene, scene_name, object_name)

    def unlink_object_from_scene(self, scene_name: str, object_name: str):
        self._sender.send_function(bl.unlink_object_from_scene, scene_name, object_name)

    def rename_scene(self, old_name: str, new_name: str):
        self._sender.send_function(bl.rename_scene, old_name, new_name)

    def rename_object(self, old_name: str, new_name: str):
        self._sender.send_function(bl.rename_object, old_name, new_name)

    def rename_collection(self, old_name: str, new_name: str):
        self._sender.send_function(bl.rename_collection, old_name, new_name)


class test_scene_empty_doc(SceneTestCase):
    def setUp(self):
        folder = Path(__file__).parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        # super().setUp(sender_blendfile, receiver_blendfile, receiver_wait_for_debugger=True)
        super().setUp(sender_blendfile, receiver_blendfile)

    def end_test(self):
        # work around a crash on change scene whend connected
        self.disconnect()
        self.assertUserSuccess()

    def test_create_scene(self):
        self.new_scene('scene_1')
        self.new_scene('scene_2')
        # temporary : create an object since update_post is not called after scene creation
        self.new_object('object_0_0')
        self.end_test()

    def test_link_collection_to_scene(self):
        self.new_collection('collection_0_0')
        self.link_collection_to_scene('Scene', 'collection_0_0')
        self.new_scene('scene_1')
        self.new_collection('collection_1_0')
        self.new_collection('collection_1_1')
        self.link_collection_to_scene('scene_1', 'collection_1_0')
        self.link_collection_to_scene('scene_1', 'collection_1_1')
        self.end_test()

    def test_unlink_collection_from_scene(self):
        self.new_collection('UNLINKED_collection_1_0')
        self.new_collection('LINKED_collection_1_1')
        self.new_scene('scene_1')
        self.link_collection_to_scene('scene_1', 'UNLINKED_collection_1_0')
        self.link_collection_to_scene('scene_1', 'LINKED_collection_1_1')
        self.unlink_collection_from_scene('scene_1', 'UNLINKED_collection_1_0')
        self.end_test()

    def test_link_object_to_scene(self):
        self.new_object('object_0_0')
        self.link_object_to_scene('Scene', 'object_0_0')
        self.new_scene('scene_1')
        self.new_object('object_1_0')
        self.new_object('object_1_1')
        self.link_object_to_scene('scene_1', 'object_1_0')
        self.link_object_to_scene('scene_1', 'object_1_1')
        self.end_test()

    def test_unlink_object_from_scene(self):
        self.new_object('UNLINKED_object_1_0')
        self.new_object('LINKED_object_1_1')
        self.new_scene('scene_1')
        self.link_object_to_scene('scene_1', 'UNLINKED_object_1_0')
        self.link_object_to_scene('scene_1', 'LINKED_object_1_1')
        self.unlink_object_from_scene('scene_1', 'UNLINKED_object_1_0')
        self.end_test()

    def test_rename_object_in_scene(self):
        self.new_object('object_1_0')
        self.new_object('OLD_object_1_1')
        self.new_scene('scene_1')
        self.link_object_to_scene('scene_1', 'object_1_0')
        self.link_object_to_scene('scene_1', 'OLD_object_1_1')
        self.rename_object('OLD_object_1_1', 'NEW_object_1_1')
        self.end_test()

    def test_rename_collection_in_scene(self):
        self.new_collection('collection_1_0')
        self.new_collection('OLD_collection_1_1')
        self.new_scene('scene_1')
        self.link_collection_to_scene('scene_1', 'collection_1_0')
        self.link_collection_to_scene('scene_1', 'OLD_collection_1_1')
        self.rename_collection('OLD_collection_1_1', 'NEW_collection_1_1')
        self.end_test()

    def test_rename_scene(self):
        self.new_scene('old_scene_1')
        self.new_object('REMOVED_object_1_0')
        self.new_collection('REMOVED_collection_1_0')
        self.link_object_to_scene('old_scene_1', 'REMOVED_object_1_0')
        self.link_collection_to_scene('old_scene_1', 'REMOVED_collection_1_0')

        self.rename_scene('old_scene_1', 'new_scene_1')

        self.new_object('kept_object_1_1')
        self.new_collection('kept_collection_1_1')
        self.link_object_to_scene('new_scene_1', 'kept_object_1_1')
        self.link_collection_to_scene('new_scene_1', 'kept_collection_1_1')

        self.unlink_object_from_scene('new_scene_1', 'REMOVED_object_1_0')
        self.unlink_collection_from_scene('new_scene_1', 'REMOVED_collection_1_0')

        self.end_test()


if __name__ == '__main__':
    unittest.main()
