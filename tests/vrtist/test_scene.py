from pathlib import Path
import unittest

from mixer.broadcaster.common import MessageType
from tests.vrtist_testcase import VRtistTestCase


class TestSceneEmptyDoc(VRtistTestCase):
    def setUp(self):
        folder = Path(__file__).parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        # super().setUp(sender_blendfile, receiver_blendfile, receiver_wait_for_debugger=True)
        super().setUp(sender_blendfile, receiver_blendfile)

    def test_create_scene(self):
        self.new_scene("scene_1")
        self.new_scene("scene_2")
        # temporary : create an object since update_post is not called after scene creation
        self.new_object("object_0_0")

        self.expected_counts = {MessageType.SCENE: 3}
        self.end_test()

    def test_link_collection_to_scene(self):
        self.new_collection("collection_0_0")
        self.link_collection_to_scene("Scene", "collection_0_0")
        self.new_scene("scene_1")
        self.new_collection("collection_1_0")
        self.new_collection("collection_1_1")
        self.link_collection_to_scene("scene_1", "collection_1_0")
        self.link_collection_to_scene("scene_1", "collection_1_1")

        self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 3}
        self.end_test()

    def test_unlink_collection_from_scene(self):
        self.new_collection("UNLINKED_collection_1_0")
        self.new_collection("LINKED_collection_1_1")
        self.new_scene("scene_1")
        self.link_collection_to_scene("scene_1", "UNLINKED_collection_1_0")
        self.link_collection_to_scene("scene_1", "LINKED_collection_1_1")
        self.unlink_collection_from_scene("scene_1", "UNLINKED_collection_1_0")

        self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 1}
        self.end_test()

    def test_link_object_to_scene(self):
        self.new_object("object_0_0")
        self.link_object_to_scene("Scene", "object_0_0")
        self.new_scene("scene_1")
        self.new_object("object_1_0")
        self.new_object("object_1_1")
        self.link_object_to_scene("scene_1", "object_1_0")
        self.link_object_to_scene("scene_1", "object_1_1")
        self.expected_counts = {MessageType.ADD_OBJECT_TO_SCENE: 3}
        self.end_test()

    def test_link_object_to_scene_twice(self):
        self.new_object("object")
        self.link_object_to_scene("Scene", "object")
        self.new_scene("scene_1")
        self.link_object_to_scene("scene_1", "object")
        self.end_test()

    def test_link_object_to_scene_and_collection(self):
        self.new_object("object")
        self.link_object_to_scene("Scene", "object")
        self.new_collection("collection")
        self.link_collection_to_scene("Scene", "collection")
        self.link_object_to_collection("collection", "object")
        self.end_test()

    def test_unlink_object_from_scene(self):
        self.new_object("UNLINKED_object_1_0")
        self.new_object("LINKED_object_1_1")
        self.new_scene("scene_1")
        self.link_object_to_scene("scene_1", "UNLINKED_object_1_0")
        self.link_object_to_scene("scene_1", "LINKED_object_1_1")
        self.unlink_object_from_scene("scene_1", "UNLINKED_object_1_0")
        self.expected_counts = {
            MessageType.REMOVE_OBJECT_FROM_SCENE: 0,
            MessageType.ADD_OBJECT_TO_SCENE: 1,
        }
        self.end_test()

    def test_rename_object_in_scene(self):
        self.new_object("object_1_0")
        self.new_object("OLD_object_1_1")
        self.new_scene("scene_1")
        self.link_object_to_scene("scene_1", "object_1_0")
        self.link_object_to_scene("scene_1", "OLD_object_1_1")
        self.rename_object("OLD_object_1_1", "NEW_object_1_1")

        self.expected_counts = {MessageType.ADD_OBJECT_TO_SCENE: 2}
        self.end_test()

    def test_rename_collection_in_scene(self):
        self.new_collection("collection_1_0")
        self.new_collection("OLD_collection_1_1")
        self.new_scene("scene_1")
        self.link_collection_to_scene("scene_1", "collection_1_0")
        self.link_collection_to_scene("scene_1", "OLD_collection_1_1")
        self.rename_collection("OLD_collection_1_1", "NEW_collection_1_1")
        self.expected_counts = {
            MessageType.ADD_COLLECTION_TO_SCENE: 2,
        }

        self.end_test()

    def test_rename_scene(self):
        self.new_scene("old_scene_1")
        self.new_object("REMOVED_object_1_0")
        self.new_collection("REMOVED_collection_1_0")
        self.link_object_to_scene("old_scene_1", "REMOVED_object_1_0")
        self.link_collection_to_scene("old_scene_1", "REMOVED_collection_1_0")

        self.rename_scene("old_scene_1", "new_scene_1")

        self.new_object("kept_object_1_1")
        self.new_collection("kept_collection_1_1")
        self.link_object_to_scene("new_scene_1", "kept_object_1_1")
        self.link_collection_to_scene("new_scene_1", "kept_collection_1_1")

        self.unlink_object_from_scene("new_scene_1", "REMOVED_object_1_0")
        self.unlink_collection_from_scene("new_scene_1", "REMOVED_collection_1_0")

        self.expected_counts = {
            MessageType.SCENE: 2,
        }
        self.end_test()

    def test_create_instance_in_scene_after_join(self):
        self.new_scene("scene_1")
        self.new_collection("src")
        self.link_collection_to_scene("scene_1", "src")
        self.create_object_in_collection("src", "object_0")
        self.new_collection_instance("src", "instance_1")
        self.link_object_to_scene("Scene", "instance_1")
        self.expected_counts = {
            MessageType.INSTANCE_COLLECTION: 1,
            MessageType.ADD_OBJECT_TO_SCENE: 1,
        }

        self.end_test()

    @unittest.skip("scene remove/rename fails in test")
    def test_create_instance_in_scene_before_join(self):
        import time

        self._sender.disconnect_mixer()
        self._receiver.disconnect_mixer()
        time.sleep(1)

        self.new_scene("scene_1")
        self.new_collection("src")
        self.link_collection_to_scene("scene_1", "src")
        self.create_object_in_collection("src", "object_0")
        self.new_collection_instance("src", "instance_1")
        self.link_object_to_scene("Scene", "instance_1")

        self._sender.connect_and_join_mixer()
        self._receiver.connect_and_join_mixer()
        self.end_test()


if __name__ == "__main__":
    unittest.main()
