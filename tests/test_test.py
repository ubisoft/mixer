import unittest
import tests.testcase as testcase
from pathlib import Path


class TestTest(testcase.BlenderTestCase):
    def setUp(self):
        # Everything will apply to the whole testcase

        folder = Path(__file__).parent
        sender_blendfile = folder / "basic.blend"
        receiver_blendfile = folder / "empty.blend"

        super().setUp(
            sender_blendfile, receiver_blendfile, sender_wait_for_debugger=False, receiver_wait_for_debugger=False
        )

    def test_selftest(self):
        pass

    # @unittest.skip("")
    def test_just_start(self):
        self.assert_user_success()

    @unittest.skip("")
    def test_this_one_fails(self):
        self.fail("failure attempt")


if __name__ == "__main__":
    unittest.main()
