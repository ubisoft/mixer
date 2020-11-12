import unittest

from parameterized import parameterized_class

from mixer.broadcaster.common import MessageType

from tests import files_folder
from tests.vrtist.vrtist_testcase import VRtistTestCase
from tests.mixer_testcase import BlenderDesc
from tests import blender_snippets as bl


class MiscTestCase(VRtistTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=VRtistTestCase.get_class_name,
)
class TestSpontaneousRename(MiscTestCase):
    def test_object_empty(self):
        self.send_strings([bl.data_objects_new("Empty", None), bl.data_objects_new("Empty", None)], to=0)

        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)
        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)
        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)
        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)

        self.send_strings([bl.data_objects_new("Another_empty", None)], to=0)

        self.assert_matches()

    def test_light(self):
        if self.vrtist_protocol:
            # use exception since the @unittest.skipIf() cannot access self
            raise unittest.SkipTest("FAILS in VRtist mode")

        self.send_strings([bl.ops_objects_light_add("POINT"), bl.ops_objects_light_add("POINT")], to=0)

        self.send_strings([bl.data_objects_rename("Point.001", "Point")], to=0)
        self.send_strings([bl.data_objects_rename("Point.001", "Point")], to=0)
        self.send_strings([bl.data_objects_rename("Point.001", "Point")], to=0)

        self.assert_matches()


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=VRtistTestCase.get_class_name,
)
class TestReferencedDatablock(MiscTestCase):
    """
    Rename datablock referenced by Object.data
    """

    def test_light(self):
        # Rename the light datablock
        if self.vrtist_protocol:
            raise unittest.SkipTest("Broken in VRtist-only")

        self.send_strings([bl.ops_objects_light_add("POINT")], to=0)
        self.send_strings([bl.data_lights_rename("Point", "__Point")], to=0)
        self.send_strings([bl.data_lights_update("__Point", ".energy = 0")], to=0)

        self.assert_matches()

    def test_material(self):
        if self.vrtist_protocol:
            raise unittest.SkipTest("Broken in VRtist-only")

        # only care about Blender_DATA_CREATE
        self.ignored_messages |= {MessageType.MATERIAL, MessageType.OBJECT_VISIBILITY}

        # This test verifies that DatablockRefProxy references of unhandled collections are correct.
        # Before fix, obj.active_material has a different uuid on both ends. This is a regression caused
        # by a9573127.

        s = """
import bpy
mesh = bpy.data.meshes.new("mesh")
obj = bpy.data.objects.new("obj", mesh)
mat = bpy.data.materials.new("mat")
obj.active_material = mat
"""
        self.send_string(s)

        self.assert_matches()

    def test_unresolved_ref_in_bpy_prop_collection(self):
        # Unresolved references stored in bpy_pro_collection

        # only care about Blender_DATA_CREATE
        self.ignored_messages |= {MessageType.MATERIAL, MessageType.OBJECT_VISIBILITY}

        # That datablock references are correctly handled even in the pointee is received after the pointer, like in
        # the Collection layout below, with collections being created (hence transmitted) in A, B, C order
        # A
        #   children C
        # B
        #   children C

        s = """
import bpy
a = bpy.data.collections.new("A")
b = bpy.data.collections.new("B")
c = bpy.data.collections.new("C")
a.children.link(c)
b.children.link(c)
"""
        self.send_string(s)

        self.assert_matches()

    @unittest.skip("TODO")
    def test_unresolved_ref_in_struct(self):
        pass


@parameterized_class(
    [{"vrtist_protocol": False}],
    class_name_func=VRtistTestCase.get_class_name,
)
class TestRenameDatablock(MiscTestCase):
    """
    Rename datablock referenced by Object.data
    """

    def test_light(self):
        # Rename the light datablock
        if self.vrtist_protocol:
            raise unittest.SkipTest("Broken in VRtist-only")

        self.send_strings([bl.ops_objects_light_add("POINT")], to=0)
        self.send_strings([bl.data_lights_rename("Point", "__Point")], to=0)
        self.send_strings([bl.data_lights_update("__Point", ".energy = 0")], to=0)

        self.assert_matches()


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=VRtistTestCase.get_class_name,
)
class TestSetDatablockRef(MiscTestCase):
    """
    Check that parenting works regardless of parent and child creation order
    """

    def test_object_parent(self):
        # 3 empties or which the creation order is not the parent order
        create = """
import bpy
scene = bpy.data.scenes[0]
obj0 = bpy.data.objects.new("obj0", None)
obj1 = bpy.data.objects.new("obj1", None)
obj2 = bpy.data.objects.new("obj2", None)
scene.collection.objects.link(obj0)
scene.collection.objects.link(obj1)
scene.collection.objects.link(obj2)
obj2.parent = obj0
obj0.parent = obj1
"""
        self.send_string(create, to=0)
        self.assert_matches()

    def test_collection_children(self):
        # Rename the light datablock
        create = """
import bpy
scene = bpy.data.scenes[0]
coll0 = bpy.data.collections.new("coll0")
coll1 = bpy.data.collections.new("coll1")
coll2 = bpy.data.collections.new("coll2")
scene.collection.children.link(coll1)
coll1.children.link(coll0)
coll0.children.link(coll2)
"""
        self.send_string(create, to=0)
        self.assert_matches()

    def test_set_datablock_ref_from_none(self):
        # 3 empties or which the creation order is not the parent order
        create = """
import bpy
scene = bpy.data.scenes[0]
obj0 = bpy.data.objects.new("obj0", None)
obj1 = bpy.data.objects.new("obj1", None)
scene.collection.objects.link(obj0)
scene.collection.objects.link(obj1)
"""
        self.send_string(create, to=0)

        set_parent = """
import bpy
scene = bpy.data.scenes[0]
obj0 = bpy.data.objects["obj0"]
obj1 = bpy.data.objects["obj1"]
obj0.parent = obj1
"""
        self.send_string(set_parent, to=0)

        self.assert_matches()

    def test_set_datablock_ref_to_none(self):

        if self.vrtist_protocol:
            raise unittest.SkipTest("Broken in VRtist-only")

        create = """
import bpy
scene = bpy.data.scenes[0]
obj0 = bpy.data.objects.new("obj0", None)
obj1 = bpy.data.objects.new("obj1", None)
scene.collection.objects.link(obj0)
scene.collection.objects.link(obj1)
obj0.parent = obj1
"""
        self.send_string(create, to=0)

        remove_parent = """
import bpy
scene = bpy.data.scenes[0]
obj0 = bpy.data.objects["obj0"]
obj0.parent = None
"""
        self.send_string(remove_parent, to=0)

        self.assert_matches()
