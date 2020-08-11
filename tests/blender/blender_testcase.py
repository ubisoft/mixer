"""
Test case for the Full Blender protocol
"""
import json
import logging
from pathlib import Path
import sys

from mixer.broadcaster.common import MessageType, decode_string
from tests.grabber import CommandStream
from tests.mixer_testcase import BlenderDesc, MixerTestCase


logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class BlenderTestCase(MixerTestCase):
    """
    Test case for the Full Blender protocol
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def assertDictAlmostEqual(self, a, b, msg=None):  # noqa N802
        def sort(d):
            return {k: d[k] for k in sorted(d.keys())}

        self.assertIs(type(a), type(b), msg=msg)
        self.assertIsInstance(a, dict, msg=msg)

        ignore = ["mixer_uuid"]
        for k in ignore:
            if k in a.keys() and k in b.keys():
                del a[k]
                del b[k]

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


class TestGeneric(BlenderTestCase):
    """Unittest that joins a room before message creation
    """

    def setUp(self, join: bool = True):
        folder = Path(__file__).parent.parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        self.set_log_level(logging.DEBUG)
        super().setUp(blenderdescs=blenderdescs, join=join)


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
