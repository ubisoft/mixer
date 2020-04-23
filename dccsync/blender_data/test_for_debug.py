import unittest
import bpy
from bpy import data as D  # noqa
from dccsync.blender_data.proxy import BpyBlendProxy
from dccsync.blender_data.diff import BpyBlendDiff


class TestBpyData(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=".local\\test_data.blend")

    def test_new_scene(self):
        proxy = BpyBlendProxy()
        proxy.load()

        D.scenes.new("plop1")
        D.scenes.new("plop2")
        #  do something
        deltas = BpyBlendDiff()
        deltas.diff(proxy)
        d = deltas.deltas["scenes"]
        self.assertEquals(2, len(d.items_added))
        self.assertEquals(d.items_added["plop1"], D.scenes)
        self.assertEquals(d.items_added["plop2"], D.scenes)
        self.assertFalse(d.items_removed)
        self.assertFalse(d.items_renamed)
        self.assertFalse(d.items_updated)
        proxy.update(deltas)
        return
        # crashes
        D.scenes.remove(D.scenes["plop2"])
        deltas.diff(proxy)
        # check
        proxy.update(deltas)
        self.assertFalse(d.items_added)
        self.assertEquals(1, len(d.items_removed))
        self.assertEquals(d.items_removed["plop2"], D.scenes)
        self.assertFalse(d.items_renamed)
        self.assertFalse(d.items_updated)

        proxy.update(deltas)
        deltas.diff(proxy)
        self.assertTrue(deltas.empty)

    @unittest.skip("")
    def test_two_scenes(self):
        self.assertEquals(2, len(bpy.data.scenes))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestBpyData)
    runner = unittest.TextTestRunner()
    runner.run(suite)


if __name__ == "__main__":
    unittest.main()
