import unittest
from tests.blender.blender_testcase import TestGenericJoinBefore


class TestBpyProxy(TestGenericJoinBefore):
    def test_just_join(self):

        self.end_test()


class TestBpyPropStructCollectionProxy(TestGenericJoinBefore):
    def test_light_falloff_curve(self):
        action = f"""
import bpy
bpy.ops.object.light_add(type='POINT')
"""
        self.send_string(action)

        # HACK it seems that we do not receive the depsgraph update
        # for light.falloff_curve.curves[0].points so ass a Light member update

        action = f"""
import bpy
light = bpy.data.lights['Point']
light.falloff_curve.curves[0].points.new(0.5, 0.5)
light.distance = 20
"""
        self.send_string(action)

        self.end_test()


if __name__ == "__main__":
    unittest.main()
