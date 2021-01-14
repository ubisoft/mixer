"""
Test case for the Full Blender protocol
"""
import logging
import sys

from tests import files_folder
from tests.mixer_testcase import BlenderDesc, MixerTestCase


logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class BlenderTestCase(MixerTestCase):
    """
    Test case for the Full Blender protocol
    """

    def __init__(self, *args, **kwargs):
        # in case @parameterized_class is missing
        if not hasattr(self, "vrtist_protocol"):
            self.vrtist_protocol = False
        super().__init__(*args, **kwargs)

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)


class TestGeneric(BlenderTestCase):
    """Unittest that joins a room before message creation"""

    def setUp(self, join: bool = True):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs, join=join)


class TestGenericJoinBefore(TestGeneric):
    """Unittest that joins a room before message creation"""

    def setUp(self):
        super().setUp(join=True)


class TestGenericJoinAfter(TestGeneric):
    """Unittest that does not join a room before message creation"""

    def setUp(self):
        super().setUp(join=False)
