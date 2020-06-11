import logging
import time
import unittest
import sys

import tests.blender_lib as bl
from tests.blender_app import BlenderApp

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class MixerTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        self._sender_wait_for_debugger = False
        self._receiver_wait_for_debugger = False
        self.expected_counts = {}
        super().__init__(*args, **kwargs)
        self._log_level = None

    def set_log_level(self, log_level):
        self._log_level = log_level

    def setUp(
        self,
        sender_blendfile=None,
        receiver_blendfile=None,
        sender_wait_for_debugger=False,
        receiver_wait_for_debugger=False,
        join=True,
    ):
        """
        if a blendfile if not specified, blender will start with its default file.
        Not recommended) as it is machine dependent
        """
        super().setUp()
        python_port = 8081
        # do not the the default ptvsd port as it will be in use when debugging the TestCase
        ptvsd_port = 5688
        sender_args = ["--window-geometry", "0", "0", "960", "1080"]
        if sender_blendfile is not None:
            sender_args.append(str(sender_blendfile))
        self._sender = BlenderApp(python_port + 0, ptvsd_port + 0, sender_wait_for_debugger)
        self._sender.set_log_level(self._log_level)
        self._sender.setup(sender_args)
        if join:
            self._sender.connect_and_join_mixer()

        receiver_args = ["--window-geometry", "960", "0", "960", "1080"]
        if receiver_blendfile is not None:
            receiver_args.append(str(receiver_blendfile))
        self._receiver = BlenderApp(python_port + 1, ptvsd_port + 1, receiver_wait_for_debugger)
        self._receiver.set_log_level(self._log_level)
        self._receiver.setup(receiver_args)
        if join:
            self._receiver.connect_and_join_mixer()

    def join(self):
        self._sender.connect_and_join_mixer()
        self._receiver.connect_and_join_mixer()

    def end_test(self):
        self.assert_matches()

    def assert_user_success(self):
        """
        Test the processes return codes, that can be set from the TestPanel UI
        """
        timeout = 0.2
        rc = None
        while True:
            rc = self._sender.wait(timeout)
            if rc is not None:
                self._receiver.kill()
                if rc != 0:
                    self.fail(f"sender return code {rc} ({hex(rc)})")
                else:
                    return

            rc = self._receiver.wait(timeout)
            if rc is not None:
                self._sender.kill()
                if rc != 0:
                    self.fail(f"receiver return code {rc} ({hex(rc)})")
                else:
                    return

    def tearDown(self):
        # quit and wait
        self._sender.quit()
        self._receiver.quit()
        self._sender.wait()
        self._receiver.wait()
        self._sender.close()
        self._receiver.close()
        super().tearDown()

    def connect(self):
        self._sender.connect_and_join_mixer()
        time.sleep(1)
        self._receiver.connect_and_join_mixer()

    def disconnect(self):
        self._sender.disconnect_mixer()
        self._receiver.disconnect_mixer()

    def send_string(self, s: str):
        self._sender.send_string(s)

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
