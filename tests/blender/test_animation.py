import unittest

from tests import files_folder
from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class TestCase(BlenderTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)


class TestAnimationData(TestCase):
    def test_animation_data_clear(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
bpy.ops.object.modifier_add(type="ARRAY")
obj = bpy.data.objects[0]
obj.modifiers[0].keyframe_insert("count")
# trigger update !
obj.hide_viewport = True
obj.hide_viewport = False
"""
        self.send_string(action)

        action = """
import bpy
obj = bpy.data.objects[0]
obj.animation_data_clear()
# trigger update !
obj.hide_viewport = True
obj.hide_viewport = False
"""
        self.send_string(action)

        self.end_test()


class TestKeyFrame(TestCase):
    def test_create_keyframe_datablock(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
obj = bpy.data.objects[0]
obj.keyframe_insert("location", index = 0)
"""
        self.send_string(action)
        self.end_test()

    def test_create_keyframe_struct(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
bpy.ops.object.modifier_add(type="ARRAY")
obj = bpy.data.objects[0]
obj.modifiers[0].keyframe_insert("count")
"""
        self.send_string(action)
        self.end_test()

    def test_create_keyframe_both(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
bpy.ops.object.modifier_add(type="ARRAY")
obj = bpy.data.objects[0]
obj.keyframe_insert("location", index = 0)
obj.modifiers[0].keyframe_insert("count")
"""
        self.send_string(action)
        self.end_test()

    def test_delete_keyframe_struct(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
bpy.ops.object.modifier_add(type="ARRAY")
obj = bpy.data.objects[0]
obj.modifiers[0].keyframe_insert("count")
"""
        self.send_string(action)

        action = """
import bpy
obj = bpy.data.objects[0]
obj.modifiers[0].keyframe_delete("count")
"""
        self.send_string(action)


class TestDriver(TestCase):
    def test_driver_add(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
obj = bpy.data.objects[0]
obj.driver_add("location", 0)
# trigger update
obj.hide_viewport = True
obj.hide_viewport = False
"""
        self.send_string(action)

        action = """
import bpy
obj = bpy.data.objects[0]
obj.driver_add("location", 1)
# trigger update
obj.hide_viewport = True
obj.hide_viewport = False
"""
        self.send_string(action)

        self.end_test()

    def test_driver_remove_one(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
obj = bpy.data.objects[0]
obj.driver_add("location")
# trigger update
obj.hide_viewport = True
obj.hide_viewport = False
"""
        self.send_string(action)

        action = """
import bpy
obj = bpy.data.objects[0]
obj.driver_remove("location", 1)
# trigger update
obj.hide_viewport = True
obj.hide_viewport = False
"""
        self.send_string(action)

        self.end_test()

    def test_add_variable(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
obj = bpy.data.objects[0]
obj.driver_add("location")
"""
        self.send_string(action)

        action = """
import bpy
obj = bpy.data.objects[0]
driver = obj.animation_data.drivers[0].driver
var = driver.variables.new()
target = var.targets[0]
target.id_type = "SCENE"
target.id = bpy.data.scenes[0]
target.data_path = "frame_current"
driver.expression = "var"
# trigger update
bpy.context.view_layer.update()
"""
        self.send_string(action)

        self.end_test()


if __name__ == "__main__":
    unittest.main()
