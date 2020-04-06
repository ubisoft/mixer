import unittest
import testcase
import blender_lib as bl
from pathlib import Path


class Test_test(testcase.BlenderTestCase):
    def setUp(self):
        # Everything will apply to the whole testcase

        folder = Path(__file__).parent
        sender_blendfile = folder / "basic.blend"
        receiver_blendfile = folder / "empty.blend"

        super().setUp(sender_blendfile, receiver_blendfile,
                      sender_wait_for_debugger=False, receiver_wait_for_debugger=False)

    @unittest.skip('')
    def test_just_start(self):
        self.assertUserSuccess()

    @unittest.skip('')
    def test_selftest(self):
        self._sender.send_function(bl.rename_mesh, 'Cube', 'Kub__')
        #self._sender.send_function(bl.add, radius=2.0, type='MESH', location=(0, 0, 2))

        # automatic file chek fails sonce the add mesh command is not transmitted at once

        self.assertMatches()


if __name__ == '__main__':
    unittest.main()
