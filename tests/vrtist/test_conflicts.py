"""
Tests for conflicting operations that are sensitive to network timings,
for instance rename a collection on one side and add to collection on the other side.

Such conflits need a server with throttling control to reproduce the problem reliably.

"""
from pathlib import Path
from typing import Set
import unittest
import time

from parameterized import parameterized_class

from mixer.broadcaster.common import MessageType

import tests.blender_snippets as bl
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
            super().setUp(blenderdescs=blenderdescs, server_args=server_args, join=False)
            for blender in self._blenders:
                blender.connect_and_join_mixer(experimental_sync=self.experimental_sync)
                # if the second join is too early it is rejected with error "room not joinable yet"
                # if the test runs too early if may run before join is complete
                time.sleep(3.0)
        except Exception:
            self.shutdown()
            raise

    def assert_matches(self):
        # Wait for the messages to reach the destination
        # TODO What os just enough ?
        time.sleep(4 * self.latency)
        super().assert_matches()


@parameterized_class(
    [{"experimental_sync": True}, {"experimental_sync": False}], class_name_func=ThrottledTestCase.get_class_name,
)
class TestSimultaneousCreate(ThrottledTestCase):
    def setUp(self):
        super().setUp("empty.blend")

    def test_empty_unlinked(self):
        empties = 2
        if not self.experimental_sync:
            self.expected_counts = {MessageType.TRANSFORM: empties}
            raise unittest.SkipTest("FAILS: Only one empty remains")
        else:
            scenes = 1
            self.expected_counts = {MessageType.BLENDER_DATA_CREATE: empties + scenes}

        create_empty = bl.data_objects_new("Empty", None)
        self.send_strings([create_empty], to=0)
        time.sleep(0.0)
        self.send_strings([create_empty], to=1)

        self.assert_matches()
        pass

    def test_empty_unlinked_many(self):
        empties = 2 * 5
        if not self.experimental_sync:
            self.expected_counts = {MessageType.TRANSFORM: empties}
            raise unittest.SkipTest("FAILS: Only half of empties remains")
        else:
            scenes = 1
            self.expected_counts = {MessageType.BLENDER_DATA_CREATE: empties + scenes}

        create_empty = bl.data_objects_new("Empty", None)
        create_empties = [create_empty] * 5
        self.send_strings(create_empties, to=0)
        time.sleep(0.0)
        self.send_strings(create_empties, to=1)

        self.assert_matches()
        pass

    def test_object_in_master_collection(self):
        lights = 2
        if not self.experimental_sync:
            self.expected_counts = {MessageType.LIGHT: lights}
            raise unittest.SkipTest("FAILS: Only one point light remains")
        else:
            scenes = 1
            # these are broken
            self.ignored_messages |= {
                MessageType.ADD_OBJECT_TO_VRTIST,
            }
            self.expected_counts = {MessageType.BLENDER_DATA_CREATE: lights + scenes}
            raise unittest.SkipTest("FAILS: see #222")

        location = "0.0, -3.0, 0.0"
        self.send_strings([bl.active_layer_master_collection() + bl.ops_objects_light_add(location=location)], to=0)

        # with a delay > latency all the messages are transmitted and the problem does not occur
        # delay = 2.0

        time.sleep(0.0)

        location = "0.0, 3.0, 0.0"
        self.send_strings([bl.active_layer_master_collection() + bl.ops_objects_light_add(location=location)], to=1)

        self.assert_matches()

        # Issue #222
        pass
