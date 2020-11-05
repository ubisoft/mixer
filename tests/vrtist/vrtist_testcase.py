"""
Test case for the VRTist protocol
"""
import logging
import sys

import tests.blender_lib as bl
from tests.mixer_testcase import MixerTestCase

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class VRtistTestCase(MixerTestCase):
    """
    Test case for the VRTist protocol

    Success is asserted by comparing the command streams issued by all participant Blenders
    """

    def __init__(self, *args, **kwargs):
        # in case @parameterized_class is missing
        if not hasattr(self, "vrtist_protocol"):
            self.vrtist_protocol = True
        super().__init__(*args, **kwargs)

    def set_active_scene(self, name: str):
        """
        Set the active scene, so that flush_collection() triggers an update.
        """
        s = f"""
import bpy
bpy.context.window.scene = bpy.data.scenes["{name}"]
"""
        self.send_string(s)

    def flush_collections(self):
        """
        Create a dummy object in order to generate a depsgraph update that catches collection creation
        in the active scene (see set_active_scene()) (HACK)
        """

        flush = """
import bpy
o = bpy.data.objects.new("empty_created_to_flush", None)
bpy.data.scenes[0].collection.objects.link(o)
"""
        self.send_string(flush)

    def end_test(self):
        self.flush_collections()
        self.assert_matches()

    def link_collection_to_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.link_collection_to_collection, parent_name, child_name)

    def create_collection_in_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.create_collection_in_collection, parent_name, child_name)

    def unlink_collection_from_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.unlink_collection_from_collection, parent_name, child_name)

    def remove_collection(self, collection_name: str):
        self._sender.send_function(bl.remove_collection, collection_name)

    def rename_collection(self, old_name: str, new_name: str):
        self._sender.send_function(bl.rename_collection, old_name, new_name)

    def create_object_in_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.create_object_in_collection, collection_name, object_name)

    def link_object_to_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.link_object_to_collection, collection_name, object_name)

    def unlink_object_from_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.unlink_object_from_collection, collection_name, object_name)

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
