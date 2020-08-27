from pathlib import Path
import unittest

from parameterized import parameterized_class

from mixer.broadcaster.common import MessageType

from tests.vrtist.vrtist_testcase import VRtistTestCase
from tests.mixer_testcase import BlenderDesc
from tests import blender_snippets as bl


@parameterized_class(
    [{"experimental_sync": True}, {"experimental_sync": False}], class_name_func=VRtistTestCase.get_class_name,
)
class TestSpontaneousRename(VRtistTestCase):
    def setUp(self):
        folder = Path(__file__).parent.parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)

    def test_object_empty(self):
        self.send_strings([bl.data_objects_new("Empty", None), bl.data_objects_new("Empty", None)], to=0)

        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)
        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)
        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)
        self.send_strings([bl.data_objects_rename("Empty.001", "Empty")], to=0)

        self.send_strings([bl.data_objects_new("Another_empty", None)], to=0)

        self.assert_matches()

    def test_light(self):
        if not self.experimental_sync:
            # use exception since the @unittest.skipIf() cannot access self
            raise unittest.SkipTest("FAILS in VRtist mode")

        self.send_strings([bl.ops_objects_light_add("POINT"), bl.ops_objects_light_add("POINT")], to=0)

        self.send_strings([bl.data_objects_rename("Point.001", "Point")], to=0)
        self.send_strings([bl.data_objects_rename("Point.001", "Point")], to=0)
        self.send_strings([bl.data_objects_rename("Point.001", "Point")], to=0)

        self.assert_matches()


@parameterized_class(
    [{"experimental_sync": True}, {"experimental_sync": False}], class_name_func=VRtistTestCase.get_class_name,
)
class TestReferencedDatablock(VRtistTestCase):
    """
    Rename datablock referenced by Object.data
    """

    def setUp(self):
        folder = Path(__file__).parent.parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)

    def test_light(self):
        # Rename the light datablock
        if not self.experimental_sync:
            raise unittest.SkipTest("Broken in VRtist-only")

        self.send_strings([bl.ops_objects_light_add("POINT")], to=0)
        self.send_strings([bl.data_lights_rename("Point", "__Point")], to=0)
        self.send_strings([bl.data_lights_update("__Point", ".energy = 0")], to=0)

        self.assert_matches()

    def test_material(self):
        if not self.experimental_sync:
            raise unittest.SkipTest("Broken in VRtist-only")

        # only care about Blender_DATA_CREATE
        self.ignored_messages |= {MessageType.MATERIAL, MessageType.OBJECT_VISIBILITY}

        # This test verifies that BpyIdRefProxy references of unhandled collections are correct.
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


@parameterized_class(
    [{"experimental_sync": True}], class_name_func=VRtistTestCase.get_class_name,
)
class TestRenameDatablock(VRtistTestCase):
    """
    Rename datablock referenced by Object.data
    """

    def setUp(self):
        folder = Path(__file__).parent.parent
        sender_blendfile = folder / "empty.blend"
        receiver_blendfile = folder / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)

    def test_light(self):
        # Rename the light datablock
        if not self.experimental_sync:
            raise unittest.SkipTest("Broken in VRtist-only")

        self.send_strings([bl.ops_objects_light_add("POINT")], to=0)
        self.send_strings([bl.data_lights_rename("Point", "__Point")], to=0)
        self.send_strings([bl.data_lights_update("__Point", ".energy = 0")], to=0)

        self.assert_matches()
