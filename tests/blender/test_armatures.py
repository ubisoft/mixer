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


override_context = """
def override_context(area_type):
    for window in bpy.context.window_manager.windows:
        for area in (area for area  in window.screen.areas if area.type == area_type):
            for region in (region for region in area.regions if region.type == 'WINDOW'):
                override = bpy.context.copy()
                override.update ( {
                    'window': window,
                    'screen': window.screen,
                    'area': area,
                    'region': region,
                    'blend_data': bpy.context.blend_data
                }
                )
                return override
    return None

def view_3d_context():
    return override_context("VIEW_3D")
"""


class TestArmatures(TestCase):
    _create = """
import bpy

ctx = view_3d_context()

bpy.ops.mesh.primitive_cylinder_add(view_3d_context())
c_obj = bpy.data.objects["Cylinder"]

bpy.ops.object.armature_add(view_3d_context(),enter_editmode = {enter_editmode})
bpy.ops.object.editmode_toggle(view_3d_context())

a_obj = bpy.data.objects["Armature"]
a_obj.data.edit_bones[0].select=True
bpy.ops.armature.subdivide(view_3d_context())
bpy.ops.object.editmode_toggle(view_3d_context())

a_obj.select_set(True)
c_obj.select_set(True)
bpy.ops.object.parent_set(view_3d_context(), type='ARMATURE_AUTO')
c_obj.select_set(False)

bpy.context.view_layer.objects.active=a_obj
a_obj.pose.bones[1].scale.z = 3.
"""

    def test_create(self):
        create = override_context + self._create.format(enter_editmode=False)
        self.send_string(create, sleep=1)

        self.end_test()

    def test_create_with_enter_editmod(self):
        create = override_context + self._create.format(enter_editmode=True)
        self.send_string(create, sleep=1)

        self.end_test()

    def test_reverse_bones_parenting(self):
        create = """
import bpy

ctx = view_3d_context()

bpy.ops.object.armature_add(view_3d_context())

bpy.ops.object.editmode_toggle(view_3d_context())
a_obj = bpy.data.objects["Armature"]
bones = a_obj.data.edit_bones
bones[0].select=True
bpy.ops.armature.subdivide(view_3d_context())
bones[1].parent = None
bones[0].parent = bones[1]
bpy.ops.object.editmode_toggle(view_3d_context())
"""
        command = override_context + create
        self.send_string(command, sleep=1)
        self.end_test()


if __name__ == "__main__":
    unittest.main()
