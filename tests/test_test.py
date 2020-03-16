import unittest
import testcase
import blender_lib as bl


class Test_test(testcase.BlenderTestCase):
    def test_selftest(self):
        self._sender.send_function(bl.rename_mesh, 'Cube', 'Kub__')
        self._sender.send_function(bl.add, radius=2.0, type='MESH', location=(0, 0, 2))
        self._sender.send_function(bl.collection_new_to_scene, 'plop')


if __name__ == '__main__':
    unittest.main()
