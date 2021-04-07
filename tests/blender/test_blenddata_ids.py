import unittest

from mixer.broadcaster.common import MessageType

from tests import files_folder
from tests.blender.blender_testcase import BlenderTestCase, TestGenericJoinBefore
from tests.mixer_testcase import BlenderDesc


class TestCase(BlenderTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)


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
bpy.ops.object.light_add(type='POINT', location=(4.0, 0.0, 0.0))
"""
        self.send_string(action)
        action = """
import bpy
D=bpy.data
light = D.lights["Point"]
light.type = "AREA"
light = light.type_recast()
light.shape = "RECTANGLE"
"""
        self.send_string(action)
        self.end_test()


class TestScene(TestGenericJoinBefore):
    def setUp(self):
        super().setUp()
        # for VRtist. Blender sends the active scene, which is not the same on sender (new scene)
        # and receiver
        self.ignored_messages |= {MessageType.SET_SCENE}

    def test_bpy_ops_scene_new(self):
        action = """
import bpy
bpy.ops.scene.new(type="NEW")
# force update
scene = bpy.context.scene
scene.unit_settings.system = "IMPERIAL"
scene.use_gravity = True
"""
        self.send_string(action)
        self.end_test()

    def test_bpy_ops_scene_delete(self):
        create = """
import bpy
bpy.ops.scene.new(type="NEW")
# force update
scene = bpy.context.scene
scene.use_gravity = True
"""
        self.send_string(create)
        delete = """
import bpy
bpy.ops.scene.delete()
"""
        self.send_string(delete)
        self.end_test()

    def test_scene_rename(self):
        create = """
import bpy
bpy.ops.scene.new(type="NEW")
# force update
scene = bpy.context.scene
scene.use_gravity = True
"""
        self.send_string(create)
        rename = """
import bpy
scene = bpy.context.scene
scene.name = "new_name"
"""
        self.send_string(rename)
        self.end_test()


class TestSceneSequencer(TestCase):
    def test_create(self):
        action = """
import bpy
scene = bpy.context.scene
seq = scene.sequence_editor.sequences
s0 = seq.new_effect(type='COLOR', name='color1', channel=1, frame_start=1, frame_end=10)
s1 = seq.new_effect(type='COLOR', name='color2', channel=2, frame_start=10, frame_end=20)
# The value read by default (0.) cannot be written. Set to a valid value
s0.strobe = 1.0
s1.strobe = 1.0
"""
        self.send_string(action)

        self.end_test()


class TestSceneViewLayer(TestCase):
    _setup = """
import bpy
scene = bpy.context.scene
vl = scene.view_layers
# makes it possible to distinguish new view layers created with NEW
vl[0].pass_alpha_threshold = 0.0
"""

    def test_add(self):
        self.send_string(self._setup)

        create = """
import bpy
bpy.ops.scene.view_layer_add(type="NEW")
# force sync
scene = bpy.context.scene
vl = scene.view_layers
vl[1].pass_alpha_threshold = 0.1
"""
        self.send_string(create)
        self.end_test()

    def test_rename(self):
        self.send_string(self._setup)

        create = """
import bpy
bpy.ops.scene.view_layer_add(type="NEW")
bpy.ops.scene.view_layer_add(type="NEW")
# force sync
scene = bpy.context.scene
vl = scene.view_layers
vl[1].pass_alpha_threshold = 0.1
vl[2].pass_alpha_threshold = 0.2
"""
        self.send_string(create)
        rename = """
import bpy
scene = bpy.context.scene
vl = scene.view_layers
vl[0].name = "vl0"
vl[1].name = "vl1"
vl[2].name = "vl2"
"""
        self.send_string(rename)
        self.end_test()

    def test_rename_conflict(self):
        create = """
import bpy
bpy.ops.scene.view_layer_add(type="NEW")
bpy.ops.scene.view_layer_add(type="NEW")
# force sync
scene = bpy.context.scene
vl = scene.view_layers
vl[1].pass_alpha_threshold = 0.1
vl[2].pass_alpha_threshold = 0.2
"""
        self.send_string(create)
        rename = """
import bpy
scene = bpy.context.scene
vl = scene.view_layers
vl[0].name = "vl"
vl[1].name = "vl" # vl.001
vl[2].name = "vl" # vl.002
vl[0].name = "vl.001" # vl.003
"""
        self.send_string(rename)
        self.end_test()

    def test_remove(self):
        create = """
import bpy
bpy.ops.scene.view_layer_add(type="NEW")
bpy.ops.scene.view_layer_add(type="NEW")
# force sync
scene = bpy.context.scene
vl = scene.view_layers
vl[1].pass_alpha_threshold = 0.1
vl[2].pass_alpha_threshold = 0.2
"""
        self.send_string(create)
        remove = """
import bpy
scene = bpy.context.scene
vl = scene.view_layers
bpy.context.window.view_layer = vl[1]
bpy.ops.scene.view_layer_remove()
"""
        self.send_string(remove)
        self.end_test()

    def test_add_blank(self):
        # synchronization of LayerCollection.exclude deserves a test since it must not be synchronized for the
        # master collection
        create = """
import bpy
bpy.ops.collection.create(name="Collection")
collection = bpy.data.collections[0]
bpy.data.scenes[0].collection.children.link(collection)
# collection is "included" in existing view layer
# and excluded from new view_layer
bpy.ops.scene.view_layer_add(type="EMPTY")
# force sync
scene = bpy.context.scene
vl = scene.view_layers
vl[1].pass_alpha_threshold = 0.1
"""
        self.send_string(create)
        self.end_test()


class TestMesh(TestGenericJoinBefore):
    def test_bpy_ops_mesh_plane_add(self):
        # Same polygon sizes
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
"""
        self.send_string(action)
        self.end_test()

    def test_edit_a_vertex_co(self):
        # Same polygon sizes
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add()
"""
        self.send_string(action)

        action = """
import bpy
bpy.data.meshes[0].vertices[0].co *= 2
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
        # change topology and resend all
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

    def test_bpy_ops_mesh_delete_all(self):
        action = """
import bpy
bpy.ops.mesh.primitive_cube_add()
"""
        self.send_string(action)

        action = """
import bpy
bpy.ops.object.editmode_toggle()
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.delete()
bpy.ops.object.editmode_toggle()
"""
        self.send_string(action)

        self.end_test()

    def test_bpy_ops_mesh_uv_texture_add(self):
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


class TestMeshVertexGroups(TestCase):
    def test_update_add_vg(self):
        # Although we send a single command, Blender triggers several DG updates and parts of the vg modifications
        # are processed as updates, not creations
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
vgs = obj.vertex_groups

bpy.ops.object.editmode_toggle()
bpy.ops.object.vertex_group_assign_new()
obj.vertex_groups[-1].name = "group_0"

bpy.ops.mesh.primitive_plane_add(location=(0., 0., 1))
bpy.ops.object.vertex_group_assign_new()
obj.vertex_groups[-1].name = "group_1"

bpy.ops.mesh.primitive_plane_add(location=(0., 0., 2))
bpy.ops.object.vertex_group_assign_new()
obj.vertex_groups[-1].name = "group_2"

bpy.ops.object.editmode_toggle()
"""
        self.send_string(action)

        self.end_test()

    def test_vg_add(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
vgs = obj.vertex_groups

bpy.ops.object.editmode_toggle()
bpy.ops.object.vertex_group_assign_new()
vgs[-1].name = "group_0"
bpy.ops.object.editmode_toggle()

"""
        self.send_string(action)

        action = """
import bpy

obj = bpy.data.objects[0]
vgs = obj.vertex_groups

bpy.ops.object.editmode_toggle()
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 1))
bpy.ops.object.vertex_group_assign_new()
vgs[-1].name = "group_1"
bpy.ops.object.editmode_toggle()
"""

        self.send_string(action)

        self.end_test()

    def test_move_vg(self):
        action = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
vgs = obj.vertex_groups

bpy.ops.object.editmode_toggle()
bpy.ops.object.vertex_group_assign_new()
obj.vertex_groups[-1].name = "group_0"

bpy.ops.mesh.primitive_plane_add(location=(0., 0., 1))
bpy.ops.object.vertex_group_assign_new()
obj.vertex_groups[-1].name = "group_1"

bpy.ops.object.editmode_toggle()
"""
        self.send_string(action)

        action = """
import bpy
bpy.ops.object.vertex_group_move(direction="UP")
"""

        self.send_string(action)
        self.end_test()


class TestObjectMaterialSlot(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_action = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]

mat0 = bpy.data.materials.new("mat0")
mat1 = bpy.data.materials.new("mat1")

bpy.ops.object.material_slot_add()
obj.material_slots[0].material = mat0

bpy.ops.object.material_slot_add()
# None

bpy.ops.object.material_slot_add()
obj.material_slots[2].link = "OBJECT"
obj.material_slots[2].material = mat1

"""

    def test_material_slots_create(self):
        # Although we send a single command, Blender triggers several DG updates and parts of the vg modifications
        # are processed as updates, not creations
        self.send_string(self._create_action)

        self.end_test()

    def test_material_slots_remove(self):
        # Although we send a single command, Blender triggers several DG updates and parts of the vg modifications
        # are processed as updates, not creations

        self.send_string(self._create_action)
        action = """
import bpy
obj = bpy.data.objects[0]
obj.active_material_index = 0
bpy.ops.object.material_slot_remove()
"""

        self.send_string(action)
        self.end_test()

    def test_material_slots_update(self):
        self.send_string(self._create_action)
        action = """
import bpy
obj = bpy.data.objects[0]
mat0 = bpy.data.materials.new("mat0")
mat1 = bpy.data.materials.new("mat1")

obj.material_slots[0].material = None
obj.material_slots[1].material = mat1
"""

        self.send_string(action)
        self.end_test()

    def test_material_slots_move(self):
        self.send_string(self._create_action)
        action = """
import bpy
obj = bpy.data.objects[0]
obj.active_material_index = 0
bpy.ops.object.material_slot_move(direction='DOWN')
"""

        self.send_string(action)
        self.end_test()


class TestObject(TestCase):
    def test_decimate_with_set_proxy(self):
        # for SetProxy
        create = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(1., 0., 0))
obj = bpy.data.objects[0]
modifier = obj.modifiers.new("decimate", "DECIMATE")
# in "planar" tab
modifier.delimit = {"SEAM", "UV"}
"""
        self.send_string(create)
        self.end_test()

    def test_parent_set(self):
        create = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(1., 0., 0))
bpy.ops.mesh.primitive_plane_add(location=(0., 1., 1))
"""
        self.send_string(create)

        parent = """
import bpy
obj0 = bpy.data.objects[0]
obj1 = bpy.data.objects[1]
bpy.context.view_layer.objects.active=obj1
obj0.select_set(True)

# obj0 is child of obj1
# the operator also modifies local_matrix and matrix_parent_inverse

bpy.ops.object.parent_set(type='OBJECT')
"""

        self.send_string(parent)
        self.end_test()


class TestShapeKey(TestCase):
    _create_on_mesh = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
obj.shape_key_add()
obj.shape_key_add()
obj.shape_key_add()
keys = bpy.data.shape_keys[0]
key0 = keys.key_blocks[0]
key0.data[0].co[2] = 1.
key1 = keys.key_blocks[1]
key1.value = 0.1
key2 = keys.key_blocks[2]
key2.value = 0.2
"""

    _create_on_curve = """
import bpy
bpy.ops.curve.primitive_bezier_circle_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
obj.shape_key_add()
obj.shape_key_add()
obj.shape_key_add()
keys = bpy.data.shape_keys[0]
key0 = keys.key_blocks[0]
key0.data[0].co[2] = 1.
key1 = keys.key_blocks[1]
key1.value = 0.1
key2 = keys.key_blocks[2]
key2.value = 0.2
"""

    def test_create_mesh(self):
        self.send_string(self._create_on_mesh)
        self.end_test()

    def test_rename_key(self):
        self.send_string(self._create_on_mesh)
        action = """
import bpy
obj = bpy.data.objects[0]
keys = bpy.data.shape_keys[0]
key0 = keys.key_blocks[0]
key0.name = "plop"
key0.data[0].co[2] = key0.data[0].co[2]
"""

        self.send_string(action)
        self.end_test()

    def test_update_relative_key(self):
        self.send_string(self._create_on_mesh)
        action = """
import bpy
obj = bpy.data.objects[0]
keys = bpy.data.shape_keys[0]
keys.key_blocks[2].relative_key = keys.key_blocks[1]
"""

        self.send_string(action)
        self.end_test()

    def test_remove_key(self):
        self.send_string(self._create_on_mesh)

        action = """
import bpy
obj = bpy.data.objects[0]
keys = bpy.data.shape_keys[0]
key1 = keys.key_blocks[1]
obj.shape_key_remove(key1)
"""
        self.send_string(action)
        self.end_test()

    def test_update_curve_handle(self):
        self.send_string(self._create_on_curve)

        action = """
import bpy
obj = bpy.data.objects[0]
keys = bpy.data.shape_keys[0]
key0 = keys.key_blocks[0]
key0.data[0].handle_left[2] = 10.
key0.data[0].handle_right[2] = 10.
"""
        self.send_string(action)
        self.end_test()


class TestCustomProperties(TestCase):
    def test_create(self):
        create = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.properties_add(data_path="active_object")
"""
        self.send_string(create)
        self.end_test()

    def test_update(self):
        create = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.properties_add(data_path="active_object")
"""
        self.send_string(create)
        update = """
import bpy
obj = bpy.data.objects[0]
rna_ui = obj["_RNA_UI"]
key = list(rna_ui.keys())[0]
rna_ui[key]["description"]= "the tooltip"
# trigger update
obj.location[0] += 1
"""
        self.send_string(update)
        self.end_test()

    def test_remove(self):
        create = """
import bpy
bpy.ops.mesh.primitive_plane_add(location=(0., 0., 0))
obj = bpy.data.objects[0]
bpy.context.view_layer.objects.active = obj
bpy.ops.wm.properties_add(data_path="active_object")
"""
        self.send_string(create)
        remove = """
import bpy
obj = bpy.data.objects[0]
rna_ui = obj["_RNA_UI"]
key = list(rna_ui.keys())[0]
bpy.ops.wm.properties_remove(data_path='active_object', property=key)
"""
        self.send_string(remove)
        self.end_test()


class TestImage(TestCase):
    def test_create_from_file(self):
        path = str(files_folder() / "image_a.png")
        create = f"""
import bpy
bpy.data.images.load(r"{path}")
"""
        self.send_string(create)
        self.end_test()


if __name__ == "__main__":
    unittest.main()
