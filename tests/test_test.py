import unittest
import testcase
import blender_lib as bl


class Test_test(testcase.BlenderTestCase):

    def test_just_start(self):
        self.assertUserSuccess()

    def test_selftest(self):
        self._sender.send_function(bl.rename_mesh, 'Cube', 'Kub__')
        self._sender.send_function(bl.add, radius=2.0, type='MESH', location=(0, 0, 2))

        # automatic file chek fails sonce the add mesh command is not transmitted at once

        self.assertUserSuccess()


if __name__ == '__main__':
    unittest.main()
