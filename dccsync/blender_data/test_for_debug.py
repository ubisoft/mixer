import unittest
import bpy
from bpy import data as D  # noqa
from dccsync.blender_data.proxy import BpyBlendProxy, BpyIDProxy, BpyIDRefProxy, BpyPropertyGroupProxy
from dccsync.blender_data.diff import BpyBlendDiff


class TestLoadProxy(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=".local\\test_data.blend")

    def test_scene(self):
        proxy = BpyBlendProxy()
        proxy.load()
        scene = proxy._data["scenes"]._data["Scene"]._data
        self.assertEqual(50, len(scene))
        objects = scene["objects"]._data
        self.assertEqual(4, len(objects))
        for o in objects.values():
            self.assertEqual(type(o), BpyIDRefProxy)

        # builtin attributes (floats)
        frame_properties = [name for name in scene.keys() if name.startswith("frame_")]
        self.assertEqual(9, len(frame_properties))

        # bpy_struct
        eevee = scene["eevee"]._data
        self.assertEqual(59, len(eevee))

        # PropertiesGroup
        cycles_proxy = scene["view_layers"]._data["View Layer"]._data["cycles"]
        self.assertTrue(isinstance(cycles_proxy, BpyPropertyGroupProxy))
        self.assertEqual(31, len(cycles_proxy._data))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestLoadProxy)
    runner = unittest.TextTestRunner()
    runner.run(suite)


if __name__ == "__main__":
    unittest.main()
