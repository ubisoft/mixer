"""
Tests for conflicting operations that are sensitive to network timings,
for instance rename a collection on one side and add to collection on the other side.

Such conflits need a server with throttling control to reproduce the problem reliably.

So far, the tests cannot really be automated on CI/CD since they require lengthy wait
until all the messages are flushed and processed at the end before grabbing
the messages from all Blender
"""
from pathlib import Path
import unittest
import time

from mixer.broadcaster.common import MessageType

from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class ThrottledTestCase(BlenderTestCase):
    def setUp(self, startup_file: str = "file2.blend"):
        try:
            files_folder = Path(__file__).parent / "files"
            file = files_folder / startup_file
            blenderdesc = BlenderDesc(load_file=file)
            blenderdescs = [blenderdesc, BlenderDesc()]

            self.latency = 1
            latency_ms = 1000 * self.latency
            server_args = ["--latency", str(latency_ms)]
            super().setUp(blenderdescs=blenderdescs, server_args=server_args)
            if not self.vrtist_protocol:
                self.ignored_messages |= {
                    # TODO clarify this
                    MessageType.ADD_OBJECT_TO_VRTIST,
                    # set to the scene displayed, which is not important as VRtist supports one scene only
                    MessageType.SET_SCENE,
                }

        except Exception:
            self.shutdown()
            raise

    def assert_matches(self):
        # Wait for the messages to reach the destination
        # TODO What os just enough ?
        time.sleep(5 * self.latency)
        super().assert_matches()


if __name__ == "__main__":
    unittest.main()
