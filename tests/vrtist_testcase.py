import hashlib
import logging
from pathlib import Path
import tempfile
import time
import sys

import tests.blender_lib as bl
from mixer.broadcaster.common import MessageType
from tests.grabber import Grabber
from tests.grabber import CommandStream
from tests.mixer_testcase import MixerTestCase


logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class VRtistTestCase(MixerTestCase):
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
            self.assertEqual(message_count, len(b[k]), f"len mismatch for {message_type}")
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

    def assert_matches(self):
        # TODO add message cout dict as param

        self._sender.disconnect_mixer()
        # time.sleep(1)
        self._receiver.disconnect_mixer()
        # time.sleep(1)

        host = "127.0.0.1"
        port = 12800
        self._sender.connect_and_join_mixer("mixer_grab_sender")
        time.sleep(1)
        sender_grabber = Grabber()
        sender_grabber.grab(host, port, "mixer_grab_sender")
        self._sender.disconnect_mixer()

        self._receiver.connect_and_join_mixer("mixer_grab_receiver")
        time.sleep(1)
        receiver_grabber = Grabber()
        receiver_grabber.grab(host, port, "mixer_grab_receiver")
        self._receiver.disconnect_mixer()

        # TODO_ timing error : sometimes succeeds
        # TODO_ enhance comparison : check # elements, understandable comparison
        s = sender_grabber.streams
        r = receiver_grabber.streams
        self.assert_stream_equals(s, r)

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

    def assert_same_files(self):
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
            self.assert_user_success()
            self.assert_files_identical(sender_file, receiver_file)

    def assert_file_exists(self, path):
        self.assertTrue(Path(path).is_file(), f"File does not exist or is not a file : {path}")

    def assert_files_identical(self, *files):
        """

        """
        if len(files) == 0:
            return

        paths = [Path(f) for f in files]
        for path in paths:
            self.assert_file_exists(path)

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
