import hashlib
import logging
from pathlib import Path
import tempfile
import time
from typing import List
import unittest

import blender_lib as bl
import dccsync_lib
from grabber import Grabber
from grabber import CommandStream
from process import BlenderServer

import sys  # noqa

sys.path.append(str(Path(__package__).parent))  # noqa
from broadcaster.common import MessageType

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)


class Blender:
    def __init__(self, port: int, ptvsd_port: int = None, wait_for_debugger=False):
        self._port = port
        self._ptvsd_port = ptvsd_port
        self._wait_for_debugger = wait_for_debugger
        self._blender: BlenderServer = None
        self._log_level = None

    def set_log_level(self, log_level: int):
        self._log_level = log_level

    def setup(self, blender_args: List = None):
        self._blender = BlenderServer(self._port, self._ptvsd_port, self._wait_for_debugger)
        self._blender.start(blender_args)
        self._blender.connect()
        self.connect_and_join_dccsync()

    def connect_and_join_dccsync(self, room_name="dccsync_unittest"):
        if self._log_level is not None:
            self._blender.send_function(dccsync_lib.set_log_level, self._log_level)
        self._blender.send_function(dccsync_lib.connect)
        self._blender.send_function(dccsync_lib.join_room, room_name)

    def disconnect_dccsync(self):
        self._blender.send_function(dccsync_lib.disconnect)

    def wait(self, timeout: float = None):
        return self._blender.wait(timeout)
        # time.sleep(60)
        # self._blender.send_function(bl.quit)

    def kill(self):
        self._blender.kill()

    def send_function(self, f, *args, **kwargs):
        self._blender.send_function(f, *args, **kwargs)
        time.sleep(1)

    def quit(self):
        self._blender.send_function(bl.quit)


class BlenderTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        self._sender_wait_for_debugger = False
        self._receiver_wait_for_debugger = False
        self.expected_counts = {}
        super().__init__(*args, **kwargs)
        self._log_level = None

    def set_log_level(self, log_level):
        self._log_level = log_level

    def assertStreamEquals(self, a_stream: CommandStream, b_stream: CommandStream, msg: str = None):
        a, b = a_stream.data, b_stream.data
        self.assertEquals(a.keys(), b.keys())

        # TODO clarify why we need to ignore TRANSFORM (float comparison)
        ignore = [MessageType.TRANSFORM]
        for k in a.keys():
            message_type = str(MessageType(k))
            message_count = len(a[k])
            self.assertEquals(message_count, len(b[k]), f"len mismatch for {message_type}")
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
                self.assertEquals(a[k], b[k], f"content mismatch for {message_type}")

    def setUp(
        self,
        sender_blendfile=None,
        receiver_blendfile=None,
        sender_wait_for_debugger=False,
        receiver_wait_for_debugger=False,
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
        self._sender = Blender(python_port + 0, ptvsd_port + 0, sender_wait_for_debugger)
        self._sender.set_log_level(self._log_level)
        self._sender.setup(sender_args)

        receiver_args = ["--window-geometry", "960", "0", "960", "1080"]
        if receiver_blendfile is not None:
            receiver_args.append(str(receiver_blendfile))
        self._receiver = Blender(python_port + 1, ptvsd_port + 1, receiver_wait_for_debugger)
        self._receiver.set_log_level(self._log_level)
        self._receiver.setup(receiver_args)

    def assertMatches(self):
        # TODO add message cout dict as param

        self._sender.disconnect_dccsync()
        # time.sleep(1)
        self._receiver.disconnect_dccsync()
        # time.sleep(1)

        host = "127.0.0.1"
        port = 12800
        self._sender.connect_and_join_dccsync("dccsync_grab_sender")
        time.sleep(1)
        sender_grabber = Grabber()
        sender_grabber.grab(host, port, "dccsync_grab_sender")
        self._sender.disconnect_dccsync()

        self._receiver.connect_and_join_dccsync("dccsync_grab_receiver")
        time.sleep(1)
        receiver_grabber = Grabber()
        receiver_grabber.grab(host, port, "dccsync_grab_receiver")
        self._receiver.disconnect_dccsync()

        # TODO_ timing error : sometimes succeeds
        # TODO_ enhance comparison : check # elements, understandable comparison
        s = sender_grabber.streams
        r = receiver_grabber.streams
        self.assertStreamEquals(s, r)

    def end_test(self):
        self.assertMatches()

    def tearDown(self):
        # quit and wait
        self._sender.quit()
        self._receiver.quit()
        self._sender.wait()
        self._receiver.wait()
        super().tearDown()

    def assertUserSuccess(self):
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

    def assertSameFiles(self):
        """
        Save and quit, then compare files

        This currently fails :
        - files are different for no apparent reason one file contains an extra Image block name Viewer Node

        """
        with Path(tempfile.mkdtemp()) as tmp_dir:
            sender_file = tmp_dir / "sender"
            receiver_file = tmp_dir / "receiver"
            self._sender.send_function(bl.save, str(sender_file))
            self._receiver.send_function(bl.save, str(receiver_file))
            self._sender.quit()
            self._receiver.quit()
            self.assertUserSuccess()
            self.assertFilesIdentical(sender_file, receiver_file)

    def assertFileExists(self, path):
        self.assertTrue(Path(path).is_file(), f"File does not exist or is not a file : {path}")

    def assertFilesIdentical(self, *files):
        """

        """
        if len(files) == 0:
            return

        paths = [Path(f) for f in files]
        for path in paths:
            self.assertFileExists(path)

        attrs = [(path, path.stat().st_size) for path in files]
        p0, s0 = attrs[0]
        for (p, s) in attrs:
            self.assertEqual(s0, s, f"File size differ for {p0} ({s0}) and {p} ({s})")

        hashes = []
        for path in paths:
            hash = hashlib.md5()
            with open(path, "rb") as f:
                hash.update(f.read())
            hashes.append((path, hash))

        p0, h0 = hashes[0]
        for (p, h) in attrs:
            self.assertEqual(h0, h, f"Hashes differ for {p0} ({h0.hex()}) and {p} ({h.hex()})")

    def connect(self):
        self._sender.connect_and_join_dccsync()
        time.sleep(1)
        self._receiver.connect_and_join_dccsync()

    def disconnect(self):
        self._sender.disconnect_dccsync()
        self._receiver.disconnect_dccsync()

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
