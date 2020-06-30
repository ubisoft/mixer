import json
import logging
from pathlib import Path
import time
import sys

from mixer.broadcaster.common import MessageType, decode_string
from tests.grabber import Grabber
from tests.grabber import CommandStream
from tests.mixer_testcase import MixerTestCase


logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class BlenderTestCase(MixerTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def assertDictAlmostEqual(self, a, b, msg=None):  # noqa N802
        def sort(d):
            return {k: d[k] for k in sorted(d.keys())}

        self.assertIs(type(a), type(b), msg=msg)
        self.assertIsInstance(a, dict, msg=msg)
        a_sorted = sort(a)
        b_sorted = sort(b)
        self.assertSequenceEqual(a.keys(), b.keys(), msg=msg)
        try:
            for (_k, ia), ib in zip(a_sorted.items(), b_sorted.values()):
                self.assertIs(type(ia), type(ib), msg=msg)
                if isinstance(ia, dict):
                    self.assertDictAlmostEqual(ia, ib, msg=msg)
                elif type(ia) is float:
                    self.assertAlmostEqual(ia, ib, places=3, msg=msg)
                else:
                    self.assertEqual(ia, ib, msg=msg)
        except AssertionError as e:
            exc_class = type(e)
            if _k == "_data":
                item = a.get("_class_name")
            else:
                item = _k
            message = f"{e.args[0]} '{item}'"
            raise exc_class(message) from None

    def assert_stream_equals(self, a_stream: CommandStream, b_stream: CommandStream, msg: str = None):
        a, b = a_stream.data, b_stream.data
        self.assertEqual(a.keys(), b.keys())

        keep = [
            MessageType.BLENDER_DATA_REMOVE,
            MessageType.BLENDER_DATA_RENAME,
            MessageType.BLENDER_DATA_UPDATE,
        ]
        for k in a.keys():
            if k not in keep:
                continue
            message_type = str(MessageType(k))
            message_count = len(a[k])
            # self.assertEqual(message_count, len(b[k]), f"len mismatch for {message_type}")
            if message_count != 0:
                logger.info(f"Message count for {message_type:16} : {message_count}")
            expected_count = self.expected_counts.get(k)
            if expected_count is not None:
                self.assertEqual(
                    expected_count,
                    message_count,
                    f"Unexpected message count for message {message_type}. Expected {expected_count}: found {message_count}",
                )
            for i, buffers in enumerate(zip(a[k], b[k])):
                strings = [decode_string(buffer, 0)[0] for buffer in buffers]
                dicts = [json.loads(string) for string in strings]
                self.assertDictAlmostEqual(*dicts, f"content mismatch for {message_type} {i}")

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
        time.sleep(0.5)
        self.assert_matches()


class TestGeneric(BlenderTestCase):
    """Unittest that joins a room before message creation
    """

    def setUp(self, join: bool = True):
        folder = Path(__file__).parent.parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        sender_wait_for_debugger = False
        receiver_wait_for_debugger = False
        self.set_log_level(logging.DEBUG)
        super().setUp(
            sender_blendfile,
            receiver_blendfile,
            sender_wait_for_debugger=sender_wait_for_debugger,
            receiver_wait_for_debugger=receiver_wait_for_debugger,
            join=join,
        )


class TestGenericJoinBefore(TestGeneric):
    """Unittest that joins a room before message creation
    """

    def setUp(self):
        super().setUp(join=True)


class TestGenericJoinAfter(TestGeneric):
    """Unittest that does not join a room before message creation
    """

    def setUp(self):
        super().setUp(join=False)
