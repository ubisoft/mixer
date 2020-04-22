import unittest
import bpy
from dccsync.blender_data.proxy import ProxyFactory, BpyDataProxy


class TestTruc(unittest.TestCase):
    def setUp(self):
        pass

    def test_one_scene(self):
        dp = BpyDataProxy().load()
        wp = ProxyFactory.make(bpy.types.BlendDataWorlds)
        wp.load(bpy.data.worlds)
        sp = ProxyFactory.make(bpy.types.BlendDataScenes)
        sp.load(bpy.data.scenes)

        cp = ProxyFactory.make(bpy.types.Camera)
        cp.load(bpy.data.cameras["Camera"])

        # cam = bpy.data.cameras["Camera"]
        # cp2 = ProxyFactory.make(cam.bl_rna)
        # cp2.load(cam)

        # sp = ProxyFactory.make(bpy.types.Scene)
        # sp.load(bpy.data.scenes[0])

        ob = ProxyFactory.make(bpy.types.Object)
        ob.load(bpy.data.objects["Cube"])

        oo = ProxyFactory.make(bpy.types.BlendDataObjects)
        oo.load(bpy.data.objects)

        vp = ProxyFactory.make(bpy.types.CameraStereoData)
        self.assertEquals(1, len(bpy.data.scenes))

    def test_two_scenes(self):
        self.assertEquals(2, len(bpy.data.scenes))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestTruc)
    runner = unittest.TextTestRunner()
    runner.run(suite)


if __name__ == "__main__":
    unittest.main()
