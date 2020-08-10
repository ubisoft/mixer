"""
Test case for the VRTist protocol
"""
import logging
import sys

from mixer.broadcaster.common import MessageType

import tests.blender_lib as bl
from tests.grabber import CommandStream
from tests.mixer_testcase import MixerTestCase


logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class VRtistTestCase(MixerTestCase):
    """
    Test case for the VRTist protocol

    Success is asserted by comparing the command streams issued by all participant Blenders
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def assert_stream_equals(self, a_stream: CommandStream, b_stream: CommandStream, msg: str = None):
        a, b = a_stream.data, b_stream.data
        self.assertEqual(a.keys(), b.keys())

        # TODO clarify why we need to ignore TRANSFORM (float comparison)
        ignore = [
            MessageType.TRANSFORM,
            MessageType.BLENDER_DATA_REMOVE,
            MessageType.BLENDER_DATA_RENAME,
            MessageType.BLENDER_DATA_UPDATE,
        ]
        for k in a.keys():
            message_type = str(MessageType(k))
            message_count = len(a[k])
            if message_count != 0:
                logger.info(f"Message count for {message_type:16} : {message_count}")
            if k not in ignore:
                expected_count = self.expected_counts.get(k)
                if expected_count is not None:
                    self.assertEqual(
                        expected_count,
                        message_count,
                        f"Unexpected message count for message {message_type}. Expected {expected_count}: found {message_count}",
                    )
                self.assertEqual(a[k], b[k], f"content mismatch for {message_type}")

    def end_test(self):
        self.assert_matches()

    def link_collection_to_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.link_collection_to_collection, parent_name, child_name)

    def create_collection_in_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.create_collection_in_collection, parent_name, child_name)

    def remove_collection_from_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.remove_collection_from_collection, parent_name, child_name)

    def remove_collection(self, collection_name: str):
        self._sender.send_function(bl.remove_collection, collection_name)

    def rename_collection(self, old_name: str, new_name: str):
        self._sender.send_function(bl.rename_collection, old_name, new_name)

    def create_object_in_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.create_object_in_collection, collection_name, object_name)

    def link_object_to_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.link_object_to_collection, collection_name, object_name)

    def remove_object_from_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.remove_object_from_collection, collection_name, object_name)

    def new_collection_instance(self, collection_name: str, instance_name: str):
        self._sender.send_function(bl.new_collection_instance, collection_name, instance_name)

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
