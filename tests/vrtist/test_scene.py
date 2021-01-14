import unittest

from parameterized import parameterized_class

from mixer.broadcaster.common import MessageType

from tests import files_folder
from tests.mixer_testcase import BlenderDesc
from tests.vrtist.vrtist_testcase import VRtistTestCase


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=VRtistTestCase.get_class_name,
)
class TestSceneEmptyDoc(VRtistTestCase):
    """
    Scene-related tests starting with an "empty" document with a single "Scene"

    Caveats for collections in generic mode:
    - collection creation do not trigger a depsgraph update, so VRtistTestCase.flush_collections() does
    a trick for this
    - the trick works if the collection is created in the active scene, so call remove_scene() so that
    the collection are created in the active scene
    """

    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        blenderdescs = [BlenderDesc(load_file=sender_blendfile), BlenderDesc(load_file=receiver_blendfile)]
        super().setUp(blenderdescs=blenderdescs)

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
        self.remove_scene("Scene")
        self.new_collection("collection_1_0")
        self.new_collection("collection_1_1")
        self.link_collection_to_scene("Scene", "collection_1_0")
        self.link_collection_to_scene("Scene", "collection_1_1")

        self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 3}
        self.end_test()

    def test_unlink_collection_from_scene(self):
        self.new_collection("UNLINKED_collection_1_0")
        self.new_collection("LINKED_collection_1_1")
        self.link_collection_to_scene("Scene", "UNLINKED_collection_1_0")
        self.link_collection_to_scene("Scene", "LINKED_collection_1_1")
        self.unlink_collection_from_scene("Scene", "UNLINKED_collection_1_0")

        self.expected_counts = {MessageType.ADD_COLLECTION_TO_SCENE: 1}
        self.end_test()

    def test_link_object_to_scene(self):
        self.new_object("object_0_0")
        self.link_object_to_scene("Scene", "object_0_0")
        self.new_object("object_1_0")
        self.new_object("object_1_1")
        self.link_object_to_scene("Scene", "object_1_0")
        self.link_object_to_scene("Scene", "object_1_1")
        self.expected_counts = {MessageType.ADD_OBJECT_TO_SCENE: 3}
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

        self.link_object_to_scene("Scene", "UNLINKED_object_1_0")
        self.link_object_to_scene("Scene", "LINKED_object_1_1")
        self.unlink_object_from_scene("Scene", "UNLINKED_object_1_0")
        self.expected_counts = {
            MessageType.REMOVE_OBJECT_FROM_SCENE: 0,
            MessageType.ADD_OBJECT_TO_SCENE: 1,
        }
        self.end_test()

    def test_rename_object_in_scene(self):
        self.new_object("object_1_0")
        self.new_object("OLD_object_1_1")

        self.link_object_to_scene("Scene", "object_1_0")
        self.link_object_to_scene("Scene", "OLD_object_1_1")
        self.rename_object("OLD_object_1_1", "NEW_object_1_1")

        self.expected_counts = {MessageType.ADD_OBJECT_TO_SCENE: 2}
        self.end_test()

    def test_rename_collection_in_scene(self):
        self.new_collection("collection_1_0")
        self.new_collection("OLD_collection_1_1")

        self.link_collection_to_scene("Scene", "collection_1_0")
        self.link_collection_to_scene("Scene", "OLD_collection_1_1")
        self.rename_collection("OLD_collection_1_1", "NEW_collection_1_1")
        self.expected_counts = {
            MessageType.ADD_COLLECTION_TO_SCENE: 2,
        }

        self.end_test()


if __name__ == "__main__":
    unittest.main()
