import unittest

from tests import files_folder
from tests.mixer_testcase import MixerTestCase


class TestTest(MixerTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "basic.blend"
        receiver_blendfile = files_folder() / "empty.blend"

        super().setUp(
            sender_blendfile, receiver_blendfile, sender_wait_for_debugger=False, receiver_wait_for_debugger=False
        )

    def test_selftest(self):
        pass

    @unittest.skip("")
    def test_just_start(self):
        self.assert_user_success()

    @unittest.skip("")
    def test_this_one_fails(self):
        self.fail("failure attempt")


if __name__ == "__main__":
    unittest.main()
