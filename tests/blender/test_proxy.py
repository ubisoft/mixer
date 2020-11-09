import unittest
from tests.blender.blender_testcase import TestGenericJoinBefore


class TestBpyProxy(TestGenericJoinBefore):
    def force_sync(self):
        action = """
import bpy
bpy.data.scenes[0].use_gravity = not bpy.data.scenes[0].use_gravity
"""
        self.send_string(action)

    def test_duplicate_uuid_metaball(self):
        # with metaballs the effect of duplicate uuids is visible as they are not
        # handled by the VRtist protocol
        action = """
import bpy
bpy.ops.object.metaball_add(type='BALL', location=(0,0,0))
obj = bpy.context.active_object
"""
        self.send_string(action)

        action = """
import bpy
D = bpy.data
bpy.ops.object.duplicate()
bpy.ops.transform.translate(value=(0, 4, 0))
"""
        self.send_string(action)

        self.force_sync()

        self.end_test()


if __name__ == "__main__":
    unittest.main()
