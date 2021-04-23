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

def node_editor_context():
    return override_context("NODE_EDITOR")
"""
create_material = """
import bpy
mat = bpy.data.materials.new("mat0")
mat.use_nodes = True

bpy.ops.mesh.primitive_cube_add()
cube = bpy.data.objects["Cube"]
bpy.ops.object.material_slot_add()
cube.material_slots[0].material = mat
"""
add_color_node = """
import bpy
node_tree = bpy.data.materials["mat0"].node_tree
principled = node_tree.nodes["Principled BSDF"]
rgb = node_tree.nodes.new("ShaderNodeRGB")
rgb.name="RGB"
from_ = rgb.outputs["Color"]
to_ = principled.inputs["Emission"]
node_tree.links.new(from_, to_)
to_ = principled.inputs["Base Color"]
node_tree.links.new(from_, to_)
"""

add_blackbody = """
import bpy
node_tree = bpy.data.materials["mat0"].node_tree
principled = node_tree.nodes["Principled BSDF"]
node = node_tree.nodes.new("ShaderNodeBlackbody")
node.name="blackbody"
from_ = node.outputs["Color"]
to_ = principled.inputs["Emission"]
node_tree.links.new(from_, to_)
to_ = principled.inputs["Subsurface Color"]
node_tree.links.new(from_, to_)
"""

remove_color_node = """
import bpy
node_tree = bpy.data.materials["mat0"].node_tree
rgb = node_tree.nodes["RGB"]
node_tree.nodes.remove(rgb)
# force a depsgraph update
bpy.data.materials["mat0"].name="mat0"
"""


class TestNodes(TestCase):
    def setUp(self):
        super().setUp()

    def test_nodes_initial_sync(self):
        action = create_material + add_color_node
        self.send_string(action)
        self.assert_matches()

    def test_nodes_add(self):
        self.send_string(create_material)
        self.send_string(add_color_node)
        self.assert_matches()

    def test_nodes_remove_last(self):
        action = create_material + add_color_node
        self.send_string(action)
        self.send_string(remove_color_node)
        self.assert_matches()

    def test_nodes_remove_third(self):
        # Remove 3td node out of 4, the type of the 4th being different
        # this triggers transferring the whole node now in 3rd position
        action = create_material + add_color_node + add_blackbody
        self.send_string(action)

        self.send_string(remove_color_node)

        update_blackbody = """
import bpy
node_tree = bpy.data.materials["mat0"].node_tree
node = node_tree.nodes["blackbody"]
node.inputs['Temperature'].default_value = 4200
# force a depsgraph update
bpy.data.materials["mat0"].name="mat0"
"""

        self.send_string(update_blackbody)

        self.assert_matches()

    def test_duplicate_node_name(self):
        # see StructCollectionProxy.apply()
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
obj = bpy.data.objects[0]
mat0 = bpy.data.materials.new("mat0")
mat0.use_nodes=True
bpy.ops.object.material_slot_add()
obj.material_slots[0].material = mat0
"""

        # see internal issue #465 and NonePtrProxy.apply() for why the action is split

        action2 = """
import bpy
mat0 = bpy.data.materials["mat0"]
node_tree = mat0.node_tree
nodes = node_tree.nodes
node1 = nodes.new("ShaderNodeTexImage")
node2 = nodes.new("ShaderNodeTexImage")
nodes.remove(node1)
node3 = nodes.new("ShaderNodeTexImage")
node_tree.links.new(node2.outputs[0], nodes["Principled BSDF"].inputs["Base Color"])
node_tree.links.new(node3.outputs[0], nodes["Principled BSDF"].inputs["Subsurface Color"])
"""

        self.send_string(action)
        self.send_string(action2)
        self.end_test()

    def test_node_reroute(self):
        action = create_material + add_blackbody
        self.send_string(action)

        add_reroute = """
import bpy
mat0 = bpy.data.materials["mat0"]
node_tree = mat0.node_tree
nodes = node_tree.nodes
nodes.new("NodeReroute")
"""
        # socket is float by default
        self.send_string(add_reroute)

        link_reroute = """
import bpy
mat0 = bpy.data.materials["mat0"]
node_tree = mat0.node_tree
nodes = node_tree.nodes
links = node_tree.links
links.new(nodes["blackbody"].outputs["Color"], nodes["Reroute"].inputs[0])
links.new(nodes["Reroute"].outputs[0], nodes["Principled BSDF"].inputs["Emission"])
"""
        # converts socket to color
        self.send_string(link_reroute)
        self.assert_matches()


class TestMaterial(TestCase):
    def test_duplicate_socket_name(self):
        # see NodeLinksProxy._load()
        # MixShader has sockets with duplicate name and the API get by name return the first only.
        # This requires identifying them by index, not my name
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
obj = bpy.data.objects[0]
mat0 = bpy.data.materials.new("mat0")
mat0.use_nodes=True
bpy.ops.object.material_slot_add()
obj.material_slots[0].material = mat0
node_tree = mat0.node_tree
nodes = node_tree.nodes
mix_node = nodes.new("ShaderNodeMixShader")
src =  nodes["Principled BSDF"].outputs["BSDF"]
dst0 = mix_node.inputs[1]
dst1 = mix_node.inputs[2]
node_tree.links.new(src, dst0)
node_tree.links.new(src, dst1)
# needed to get a depsgraph update
node_tree.links.new(mix_node.outputs[0], nodes["Material Output"].inputs[1])
"""
        self.send_string(action)
        self.end_test()


class TestNodeGroups(TestCase):
    add_nodes = """
import bpy
node_tree = bpy.data.materials["mat0"].node_tree
principled = node_tree.nodes["Principled BSDF"]
rgb1 = node_tree.nodes.new("ShaderNodeRGB")
rgb1.name="RGB1"
rgb2 = node_tree.nodes.new("ShaderNodeRGB")
rgb2.name="RGB2"
mix = node_tree.nodes.new("ShaderNodeMixRGB")
mix.name="MIX"
node_tree.links.new(mix.outputs["Color"], principled.inputs["Base Color"])
node_tree.links.new(rgb1.outputs["Color"], mix.inputs["Color1"])
node_tree.links.new(rgb2.outputs["Color"], mix.inputs["Color2"])
for node in node_tree.nodes:
    node.select = False
"""
    # https://blenderartists.org/t/best-way-to-group-nodes/576043/4
    create_group = (
        override_context
        + """
import bpy
node_tree = bpy.data.materials["mat0"].node_tree
nodes = node_tree.nodes
nodes["MIX"].select = True
nodes["RGB1"].select = True
ctx = node_editor_context()
bpy.ops.node.group_make(ctx)
"""
    )
    add_input = """
import bpy
node_tree = bpy.data.node_groups[0]
new_tree_input = node_tree.inputs.new("NodeSocketColor", "new_color")
nodes = node_tree.nodes
sock = node_tree.nodes["Group Input"].outputs[new_tree_input.name]
node_tree.links.new(sock, nodes["MIX"].inputs["Color1"])
"""

    def test_create_group(self):
        self.send_string(create_material)
        self.send_string(self.add_nodes)
        self.send_string(self.create_group)
        self.end_test()

    def test_add_interface(self):
        self.send_string(create_material)
        self.send_string(self.add_nodes)
        self.send_string(self.create_group)

        self.send_string(self.add_input)
        self.end_test()

    @unittest.skip("node group socked default value comparison fails")
    def test_move_interface(self):
        # after move_socket, the default value of the group input sockets do not match
        self.send_string(create_material)
        self.send_string(self.add_nodes)
        self.send_string(self.create_group)
        self.send_string(self.add_input)

        # the node group is already open in the node editor
        move_socket = """
import bpy
node_tree = bpy.data.node_groups[0]
print(node_tree)
node_tree.active_input = 0
bpy.ops.node.tree_socket_move(node_editor_context(), direction='DOWN', in_out='IN')
bpy.data.materials[0].node_group.nodes.new("ShaderNodeRGB")
"""
        self.send_string(override_context + move_socket)

        self.end_test()


class TestGeometryNodes(TestCase):
    create = """
import bpy
from bpy import context as C
if bpy.app.version >= (2, 92, 0):
    bpy.ops.mesh.primitive_cube_add()
    cube = C.active_object
    cube.scale *= 0.1
    bpy.ops.mesh.primitive_plane_add()
    plane = C.active_object
    plane.scale *= 10
    bpy.ops.object.modifier_add(type='NODES')
    ng = plane.modifiers[0].node_group
    point_distribute=ng.nodes.new("GeometryNodePointDistribute")
    point_distribute.inputs["Density Max"].default_value = 2
    randomize=ng.nodes.new("GeometryNodeAttributeRandomize")
    randomize.inputs["Attribute"].default_value = "scale"
    randomize.inputs[5].default_value = 0.2
    point_instance=ng.nodes.new("GeometryNodePointInstance")
    point_instance.inputs["Object"].default_value = cube
    in_ = ng.nodes["Group Input"]
    out_ = ng.nodes["Group Output"]
    ng.links.new(in_.outputs["Geometry"], point_distribute.inputs["Geometry"])
    ng.links.new(point_distribute.outputs["Geometry"], randomize.inputs["Geometry"])
    ng.links.new(randomize.outputs["Geometry"], point_instance.inputs["Geometry"])
    ng.links.new(point_instance.outputs["Geometry"], out_.inputs["Geometry"])
"""

    def test_create(self):
        self.send_string(self.create, sleep=2.0)

        hack = """
import bpy
if bpy.app.version >= (2, 92, 0):
    bpy.data.objects[0].name = bpy.data.objects[0].name
"""
        self.send_string(hack, to=1, sleep=2.0)
        self.end_test()

    @unittest.skip("Randomly fails")
    def test_input_int(self):
        # Input float has a bug before 2.93 https://developer.blender.org/T86876
        self.send_string(self.create)

        update = """
import bpy
plane = bpy.data.objects["Plane"]
modifier = plane.modifiers[0]
ng = modifier.node_group
sock = ng.inputs.new(name= "in_i", type = "NodeSocketInt")
ng.links.new(ng.nodes["Group Input"].outputs["in_i"], ng.nodes["Point Distribute"].inputs["Density Max"])
modifier[sock.identifier] = 10
modifier.show_viewport = False
modifier.show_viewport = True
"""
        self.send_string(update, sleep=5)
        self.end_test()


if __name__ == "main":
    unittest.main()
