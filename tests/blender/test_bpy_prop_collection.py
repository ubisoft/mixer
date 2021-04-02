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


class GreasePenciltestCase(TestCase):
    def assert_matches(self):
        # HACK GPencilLayer.thickness default value is 0, but the allowed range is [1..10],
        # so 0 is read in the sender, but writing 0 in the receiver sets the value to 1 !
        ignore = "thickness"
        super().assert_matches(ignore=ignore)


class TestMetaballElements(TestCase):
    """"""

    def test_add(self):
        create = """
import bpy
bpy.ops.object.metaball_add(type='BALL')
bpy.context.active_object.data.elements[0].co.x += 0
bpy.ops.object.editmode_toggle()
"""
        self.send_string(create, to=0)

        metaball_add = """
import bpy
# add in edit mode adds an element
bpy.ops.object.metaball_add(type='PLANE')
bpy.context.active_object.data.elements[1].co.x += 5
bpy.ops.object.editmode_toggle()
"""
        self.send_string(metaball_add, to=0)

        self.assert_matches()

    def test_remove(self):
        create = """
import bpy
bpy.ops.object.metaball_add(type='BALL')
bpy.context.active_object.data.elements[0].co.x += 0
bpy.ops.object.editmode_toggle()
bpy.ops.object.metaball_add(type='PLANE')
bpy.context.active_object.data.elements[1].co.x += 5
bpy.ops.object.metaball_add(type='CAPSULE')
bpy.context.active_object.data.elements[2].co.x += 10
bpy.ops.object.editmode_toggle()
"""
        self.send_string(create, to=0)

        metaball_remove = """
import bpy
# add in edit mode adds an element
elements = bpy.context.active_object.data.elements
elements.remove(elements[0])
bpy.ops.object.editmode_toggle()
"""
        self.send_string(metaball_remove, to=0)

        self.assert_matches()


class TestGreasePencilModifier(GreasePenciltestCase):
    def test_add(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
"""
        self.send_string(create, to=0)

        layer_add = """
import bpy
bpy.ops.object.gpencil_modifier_add(type='GP_ARRAY')
bpy.ops.object.gpencil_modifier_add(type='GP_NOISE')
"""
        self.send_string(layer_add, to=0)

        self.assert_matches()

    def test_move_down(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
bpy.ops.object.gpencil_modifier_add(type='GP_ARRAY')
bpy.ops.object.gpencil_modifier_add(type='GP_NOISE')
"""
        self.send_string(create, to=0)

        layer_add = """
import bpy
bpy.ops.object.gpencil_modifier_move_down(modifier='Array')
"""
        self.send_string(layer_add, to=0)

        self.assert_matches()


class TestGreasePencilLayer(GreasePenciltestCase):
    def test_add(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
"""
        self.send_string(create, to=0)

        layer_add = """
import bpy
bpy.ops.gpencil.layer_add()
"""
        self.send_string(layer_add, to=0)

        self.assert_matches()

    def test_remove_first(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
"""
        self.send_string(create, to=0)

        layer_remove = """
import bpy
bpy.ops.gpencil.layer_active(layer=1)
bpy.ops.gpencil.layer_remove()
"""
        self.send_string(layer_remove, to=0)

        self.assert_matches()

    def test_remove_middle(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
bpy.ops.gpencil.layer_add()
"""
        self.send_string(create, to=0)

        layer_remove = """
import bpy
bpy.ops.gpencil.layer_active(layer=1)
bpy.ops.gpencil.layer_remove()
"""
        self.send_string(layer_remove, to=0)

        self.assert_matches()

    def test_move(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
"""
        self.send_string(create, to=0)

        layer_move = """
import bpy
# 1 is top
bpy.context.scene.objects.active = bpy.data.grease_pencils[0]
bpy.ops.gpencil.layer_active(layer=1)
bpy.ops.gpencil.layer_move(type='DOWN')
"""
        self.send_string(layer_move, to=0)

        self.assert_matches()

    def test_merge(self):
        create = """
import bpy
bpy.ops.object.gpencil_add(type='MONKEY')
"""
        self.send_string(create, to=0)

        layer_merge = """
import bpy
# 1 is top
bpy.ops.gpencil.layer_active(layer=1)
bpy.ops.gpencil.layer_merge()
"""
        self.send_string(layer_merge, to=0)

        self.assert_matches()


class TestObjectModifier(TestCase):
    def test_add(self):
        create = """
import bpy
bpy.ops.mesh.primitive_cube_add()
"""
        self.send_string(create, to=0)

        add_modifiers = """
import bpy
bpy.ops.object.modifier_add(type='ARRAY')
bpy.ops.object.modifier_add(type='SUBSURF')
"""
        self.send_string(add_modifiers, to=0)

        self.assert_matches()

    def test_move_down(self):
        create = """
import bpy
bpy.ops.mesh.primitive_cube_add()
bpy.ops.object.modifier_add(type='ARRAY')
bpy.ops.object.modifier_add(type='SUBSURF')
"""
        self.send_string(create, to=0)

        add_modifiers = """
import bpy
bpy.ops.object.modifier_move_down(modifier='Array')
"""
        self.send_string(add_modifiers, to=0)

        self.assert_matches()


class TestObjectVertexGroup(TestCase):
    # Test only Object.vertex_groups, without Mesh data
    def test_add(self):
        create = """
import bpy
bpy.ops.mesh.primitive_cube_add()
"""
        self.send_string(create, to=0)

        add_vertex_groups = """
import bpy
bpy.ops.object.vertex_group_add()
bpy.ops.object.vertex_group_add()
"""
        self.send_string(add_vertex_groups, to=0)

        self.assert_matches()

    def test_move_last_up(self):
        create = """
import bpy
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.active_object
bpy.ops.object.vertex_group_add()
bpy.ops.object.vertex_group_add()
# 0 is top
obj.vertex_groups[0].name = "vg0"
obj.vertex_groups[1].name = "vg1"
"""
        self.send_string(create, to=0)

        move = """
import bpy
bpy.ops.object.vertex_group_move(direction="UP")
"""
        self.send_string(move, to=0)

        self.assert_matches()


class TestCurveMapPoints(TestCase):
    def test_light_falloff_curve_add_point(self):
        action = """
import bpy
bpy.ops.object.light_add(type='POINT')
"""
        self.send_string(action)

        # HACK it seems that we do not receive the depsgraph update
        # for light.falloff_curve.curves[0].points so add a Light member update

        action = """
import bpy
light = bpy.data.lights['Point']
light.falloff_curve.curves[0].points.new(0.5, 0.5)
light.distance = 20
"""
        self.send_string(action)

        self.assert_matches()


class TestRenderViews(TestCase):
    def test_scene_render_view_add_remove(self):
        action = """
import bpy
views = bpy.data.scenes[0].render.views
bpy.ops.scene.render_view_add()
index = views.active_index
views[2].use = False
views.remove(views[0])
"""
        self.send_string(action)

        self.assert_matches()


class TestCurveMapping(TestCase):
    @unittest.skip("see internal issue #298")
    def test_scene_color_management_curve(self):
        action = """
import bpy
settings = bpy.data.scenes[0].view_settings
settings.use_curve_mapping = True
rgb = settings.curve_mapping.curves[3]
points = rgb.points
points.new(0.2, 0.8)
points.new(0.7, 0.3)
"""
        self.send_string(action)

        self.assert_matches()


if __name__ == "main":
    unittest.main()
