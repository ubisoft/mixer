import unittest
from tests.blender.blender_testcase import TestGenericJoinBefore


class TestBpyProxy(TestGenericJoinBefore):
    def test_just_join(self):

        self.end_test()


class TestBpyPropStructCollectionProxy(TestGenericJoinBefore):
    def test_light_falloff_curve_add_point(self):
        action = f"""
import bpy
bpy.ops.object.light_add(type='POINT')
"""
        self.send_string(action)

        # HACK it seems that we do not receive the depsgraph update
        # for light.falloff_curve.curves[0].points so add a Light member update

        action = f"""
import bpy
light = bpy.data.lights['Point']
light.falloff_curve.curves[0].points.new(0.5, 0.5)
light.distance = 20
"""
        self.send_string(action)

        self.end_test()

    def test_scene_render_view_add_remove(self):
        action = f"""
import bpy
views = bpy.data.scenes[0].render.views
bpy.ops.scene.render_view_add()
index = views.active_index
views[2].use = False
views.remove(views[0])
"""
        self.send_string(action)

        self.end_test()

    def test_scene_color_management_curve(self):
        action = f"""
import bpy
settings = bpy.data.scenes[0].view_settings
settings.use_curve_mapping = True
rgb = settings.curve_mapping.curves[3]
points = rgb.points
points.new(0.2, 0.8)
points.new(0.7, 0.3)
"""
        self.send_string(action)

        self.end_test()


if __name__ == "__main__":
    unittest.main()
