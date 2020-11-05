import unittest

from parameterized import parameterized_class

from tests import files_folder
from tests.mixer_testcase import BlenderDesc
from tests.vrtist.vrtist_testcase import VRtistTestCase


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}],
    class_name_func=VRtistTestCase.get_class_name,
)
class TestCollection(VRtistTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "basic.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)

    def test_create_collection_in_collection(self):
        self.new_collection("plop")
        self.link_collection_to_collection("Collection", "plop")
        self.new_collection("plaf")
        self.link_collection_to_collection("Collection", "plaf")
        self.new_collection("sous_plop")
        self.link_collection_to_collection("plop", "sous_plop")
        self.new_collection("sous_plaf")
        self.link_collection_to_collection("plaf", "sous_plaf")
        self.assert_matches()

    def test_create_collection_linked_twice(self):
        self.new_collection("C1")
        self.new_collection("C2")
        self.link_collection_to_collection("Collection", "C1")
        self.link_collection_to_collection("Collection", "C2")
        self.new_collection("CC")
        self.link_collection_to_collection("C1", "CC")
        self.link_collection_to_collection("C2", "CC")
        self.assert_matches()

    def test_create_collection_in_collection_1(self):
        self.new_collection("plop")
        self.link_collection_to_collection("Collection", "plop")
        self.new_collection("plaf")
        self.link_collection_to_collection("Collection", "plaf")
        # it used to fail in this order and work after collection rename
        # so keep the test
        self.new_collection("sous_plaf")
        self.link_collection_to_collection("plaf", "sous_plaf")
        self.new_collection("sous_plop")
        self.link_collection_to_collection("plop", "sous_plop")
        self.assert_matches()

    def test_create_collection_in_collection_name_clash(self):
        self.create_collection_in_collection("Collection", "plop")
        self.create_collection_in_collection("Collection", "Collection")
        self.create_collection_in_collection("plop", "plop")
        self.assert_matches()

    def test_create_object(self):
        self.create_object_in_collection("Collection", "new_object_0_0")
        self.create_object_in_collection("Collection", "new_object_0_1")
        self.create_collection_in_collection("Collection", "sub_collection_0")
        self.create_object_in_collection("sub_collection_0", "new_object_0_2")
        self.assert_matches()

    def test_create_object_linked(self):
        self.new_collection("C1")
        self.new_collection("C2")
        self.link_collection_to_collection("Collection", "C1")
        self.link_collection_to_collection("Collection", "C2")
        self.new_object("OO")
        self.link_object_to_collection("Collection", "OO")
        self.link_object_to_collection("C1", "OO")
        self.link_object_to_collection("C2", "OO")
        self.assert_matches()

    def test_remove_object_from_collection(self):
        self.create_collection_in_collection("Collection", "sub_collection_1")
        self.create_object_in_collection("Collection", "new_object_0_0")
        self.create_object_in_collection("Collection", "new_object_0_1")
        self.create_object_in_collection("sub_collection_1", "new_object_1_0")
        self.create_object_in_collection("sub_collection_1", "new_object_1_1")

        self.unlink_object_from_collection("Collection", "new_object_0_0")
        self.unlink_object_from_collection("Collection", "new_object_0_1")
        self.unlink_object_from_collection("sub_collection_1", "new_object_1_0")
        self.unlink_object_from_collection("sub_collection_1", "new_object_1_1")
        self.assert_matches()

    def test_remove_collection_from_collection(self):
        self.create_collection_in_collection("Collection", "plaf0")
        self.create_collection_in_collection("Collection", "plaf1")
        self.unlink_collection_from_collection("Collection", "plaf0")
        self.unlink_collection_from_collection("Collection", "plaf1")

        self.remove_collection("plaf0")
        self.remove_collection("plaf1")

        self.create_collection_in_collection("Collection", "plaf1")
        self.unlink_collection_from_collection("Collection", "plaf1")
        self.assert_matches()

    def test_create_instance_in_collection_after_join(self):
        self.create_collection_in_collection("Collection", "src")
        self.create_object_in_collection("src", "new_object_0_0")
        self.create_collection_in_collection("Collection", "dst")
        self.new_collection_instance("src", "src_instance_in_Collection")
        self.new_collection_instance("src", "src_instance_in_dst")
        self.link_object_to_collection("Collection", "src_instance_in_Collection")
        self.link_object_to_collection("dst", "src_instance_in_dst")
        self.assert_matches()

    @unittest.skip("Timing problem")
    def test_create_instance_in_collection_before_join(self):
        """
        This test causes an exception in the second connection in the receiver sharedData.current_statistics
        is not initialized.
        """

        # if collection instances are create before join we need to ensure that
        # the collection is received before the instance

        self._sender.disconnect_mixer()
        self._receiver.disconnect_mixer()
        self.create_collection_in_collection("Collection", "src")
        self.create_object_in_collection("src", "new_object_0_0")
        self.create_collection_in_collection("Collection", "dst")
        self.new_collection_instance("src", "src_instance_in_Collection")
        self.new_collection_instance("src", "src_instance_in_dst")
        self.link_object_to_collection("Collection", "src_instance_in_Collection")
        self.link_object_to_collection("dst", "src_instance_in_dst")
        self._sender.connect_and_join_mixer(vrtist_protocol=self.vrtist_protocol)
        self._receiver.connect_and_join_mixer(vrtist_protocol=self.vrtist_protocol)
        self.assert_matches()

    def test_rename_collection(self):
        self.create_collection_in_collection("Collection", "old_name")
        self.create_object_in_collection("old_name", "object_0")
        self.create_object_in_collection("old_name", "object_1")
        self.create_collection_in_collection("old_name", "collection_0_old")
        self.create_collection_in_collection("old_name", "collection_1_old")
        self.create_object_in_collection("collection_0_old", "object_0_0")

        self.rename_collection("collection_1_old", "collection_1_new")
        self.rename_collection("old_name", "new_name")
        self.rename_collection("collection_0_old", "collection_0_new")
        self.assert_matches()


@parameterized_class(
    [{"vrtist_protocol": False}, {"vrtist_protocol": True}], class_name_func=VRtistTestCase.get_class_name
)
class TestCollectionFromEmpty(VRtistTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)

    def test_rename_collection_2(self):
        # need to be linked to master collection in order to get depsgraph updates
        s = """
import bpy
c1 = bpy.data.collections.new("c1")
master = bpy.data.scenes[0].view_layers[0].layer_collection.collection
master.children.link(c1)
c2 = bpy.data.collections.new("c2")
c1.children.link(c2)
"""
        self.send_string(s)

        s = """
import bpy
c1 = bpy.data.collections["c1"]
c1.name = "c1_updated"
"""
        self.send_string(s)

        self.assert_matches()

    def test_rename_unlink_object(self):
        s = """
import bpy
c1 = bpy.data.collections.new("c1")
master = bpy.data.scenes[0].view_layers[0].layer_collection.collection
master.children.link(c1)
c2 = bpy.data.collections.new("c2")
obj = bpy.data.objects.new("obj", None)
c1.children.link(c2)
c2.objects.link(obj)
"""
        self.send_string(s)

        s = """
import bpy
c1 = bpy.data.collections["c1"]
c2 = bpy.data.collections["c2"]
obj = bpy.data.objects["obj"]
c1.name = "c1_updated"
c1.objects.unlink(obj)
"""
        self.send_string(s)

        self.assert_matches()

    def test_rename_unlink_object_2(self):
        s = """
import bpy
c1 = bpy.data.collections.new("c1")
master = bpy.data.scenes[0].view_layers[0].layer_collection.collection
master.children.link(c1)
c2 = bpy.data.collections.new("c2")
obj = bpy.data.objects.new("obj", None)
c1.children.link(c2)
c2.objects.link(obj)
"""
        self.send_string(s)

        s = """
import bpy
c2 = bpy.data.collections["c2"]
obj = bpy.data.objects["obj"]
c2.name = "c2_updated"
c2.objects.unlink(obj)
"""
        self.send_string(s)

        # on receiver c2_updated exists but is not linked to c1
        self.assert_matches()

    def test_collection_unlink_object_4(self):
        s = """
import bpy
c1 = bpy.data.collections.new("c1")
c2 = bpy.data.collections.new("c2")
c3 = bpy.data.collections.new("c3")
c1.children.link(c2)
c2.children.link(c3)
"""
        self.send_string(s)

        s = """
import bpy
c2 = bpy.data.collections["c2"]
c3 = bpy.data.collections["c3"]
c2.name = "c2_updated"
"""
        self.send_string(s)

    def test_rename_unlink_object3(self):
        s = """
import bpy
master = bpy.data.scenes[0].view_layers[0].layer_collection.collection
c1 = bpy.data.collections.new("c1")
c2 = bpy.data.collections.new("c2")
c3 = bpy.data.collections.new("c3")
obj = bpy.data.objects.new("obj", None)
master.children.link(c1)
c1.children.link(c2)
c2.children.link(c3)
c2.objects.link(obj)
"""
        self.send_string(s)

        s = """
import bpy
c2 = bpy.data.collections["c2"]
c3 = bpy.data.collections["c3"]
obj = bpy.data.objects["obj"]
c2.name = "c2_updated"
c2.objects.unlink(obj)
"""
        # obj is not unlinked on receiver
        self.send_string(s)

        self.assert_matches()


if __name__ == "__main__":
    unittest.main()
