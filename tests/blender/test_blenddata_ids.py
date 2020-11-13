import unittest
from tests.blender.blender_testcase import TestGenericJoinBefore


class TestMetaBall(TestGenericJoinBefore):
    def test_bpy_data_new(self):
        create_metaball = """
import bpy
name = "mb1"
mb = bpy.data.metaballs.new(name)
e1 = mb.elements.new(type="CAPSULE")
e1.co = (1, 1, 1)
e1.radius=3
e2 = mb.elements.new(type="BALL")
e2.co = (-1, -1, -1)
obj = bpy.data.objects.new(name, mb)
bpy.data.scenes[0].collection.objects.link(obj)
e2.type = "PLANE"
"""
        self.send_string(create_metaball)
        self.end_test()

    def test_bpy_ops_object_add(self):
        action = """
import bpy
bpy.ops.object.metaball_add(type='PLANE', location=(1.0, 1.0, 1.0))
o1 = bpy.context.active_object
bpy.ops.object.metaball_add(type='CAPSULE', location=(0.0, 0.0, 0.0))
bpy.ops.object.metaball_add(type='BALL', location=(-1.0, -1.0, -1.0))
"""
        self.send_string(action)
        self.end_test()

    def test_add_remove(self):
        action = """
import bpy
bpy.ops.object.metaball_add(type='CAPSULE', location=(0.0, 0.0, 0.0))
bpy.ops.object.metaball_add(type='PLANE', location=(1.0, 1.0, 1.0))
bpy.ops.object.metaball_add(type='BALL', location=(-1.0, -1.0, -1.0))
"""
        self.send_string(action)
        action = """
name = "Mball.001"
import bpy
D=bpy.data
D.objects.remove(D.objects[name])
D.metaballs.remove(D.metaballs[name])
"""
        self.send_string(action)

        self.end_test()


class TestLight(TestGenericJoinBefore):
    def test_bpy_ops_object_add(self):
        action = """
import bpy
bpy.ops.object.light_add(type='POINT', location=(0.0, 0.0, 0.0))
bpy.ops.object.light_add(type='SUN', location=(2.0, 0.0, 0.0))
bpy.ops.object.light_add(type='AREA', location=(4.0, 0.0, 0.0))
"""
        self.send_string(action)
        self.end_test()

    def test_change_area_attrs(self):
        action = """
import bpy
bpy.ops.object.light_add(type='AREA', location=(4.0, 0.0, 0.0))
"""
        self.send_string(action)
        action = """
import bpy
D=bpy.data
area = D.lights["Area"]
area.size = 5
area.shape = 'DISK'
"""
        self.send_string(action)
        self.end_test()

    def test_morph_light(self):
        action = """
import bpy
bpy.ops.object.light_add(type='AREA', location=(4.0, 0.0, 0.0))
"""
        self.send_string(action)
        action = """
import bpy
D=bpy.data
light = D.lights["Area"]
light.type = "SUN"
"""
        self.send_string(action)
        self.end_test()


class TestScene(TestGenericJoinBefore):
    def test_bpy_ops_scene_new(self):
        action = """
import bpy
scene = bpy.ops.scene_new(type="NEW")
print(scene)
print(f"new scene is {scene}")
scene.unit_settings.system = "IMPERIAL"
scene.use_gravity = True
"""
        self.send_string(action)
        self.end_test()


class TestMesh(TestGenericJoinBefore):
    def test_bpy_ops_mesh_plane_add(self):
        """Same polygon sizes"""
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
"""
        self.send_string(action)
        self.end_test()

    def test_bpy_ops_mesh_cone_add(self):
        # Different polygon sizes
        action = """
import bpy
bpy.ops.mesh.primitive_cone_add()
"""
        self.send_string(action)
        self.end_test()

    def test_bpy_ops_mesh_subdivide(self):
        """Different polygon sizes"""
        action = """
import bpy
bpy.ops.mesh.primitive_cone_add()
"""
        self.send_string(action)

        action = """
import bpy
bpy.ops.object.editmode_toggle()
bpy.ops.mesh.subdivide()
bpy.ops.object.editmode_toggle()
"""
        self.send_string(action)

        self.end_test()

    def test_bpy_ops_mesh_uv_texture_add(self):
        """Different polygon sizes"""
        action = """
import bpy
bpy.ops.mesh.primitive_cone_add()
"""
        self.send_string(action)

        action = """
import bpy
bpy.ops.mesh.uv_texture_add()
"""
        self.send_string(action)

        self.end_test()


if __name__ == "__main__":
    unittest.main()
