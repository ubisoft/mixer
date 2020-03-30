import unittest
import testcase
from pathlib import Path
import blender_lib as bl


class CollectionTestCase(testcase.BlenderTestCase):
    pass


class test_collection_default_doc(CollectionTestCase):
    def setUp(self):
        folder = Path(__file__).parent
        sender_blendfile = folder / "basic.blend"
        receiver_blendfile = folder / "empty.blend"
        super().setUp(sender_blendfile, receiver_blendfile)

    def test_create_collection_in_collection(self):
        self.create_collection_in_collection('Collection', 'plop')
        self.create_collection_in_collection('Collection', 'plaf')
        self.create_collection_in_collection('plop', 'sous_plop')
        self.create_collection_in_collection('plaf', 'sous_plaf')
        self.assertUserSuccess()

    def test_create_collection_in_collection_1(self):
        self.create_collection_in_collection('Collection', 'plop')
        self.create_collection_in_collection('Collection', 'plaf')
        # it used to fail in this order and work after collection rename
        # so keep the test
        self.create_collection_in_collection('plaf', 'sous_plaf')
        self.create_collection_in_collection('plop', 'sous_plop')
        self.assertUserSuccess()

    def test_create_collection_in_collection_name_clash(self):
        self.create_collection_in_collection('Collection', 'plop')
        self.create_collection_in_collection('Collection', 'Collection')
        self.create_collection_in_collection('plop', 'plop')
        self.assertUserSuccess()

    def test_create_object_in_collection(self):
        self.create_object_in_collection('Collection', 'new_object_0_0')
        self.create_object_in_collection('Collection', 'new_object_0_1')
        self.create_collection_in_collection('Collection', 'sub_collection_0')
        self.create_object_in_collection('sub_collection_0', 'new_object_0_2')
        self.assertUserSuccess()

    def test_remove_object_from_collection(self):
        self.create_collection_in_collection('Collection', 'sub_collection_1')
        self.create_object_in_collection('Collection', 'new_object_0_0')
        self.create_object_in_collection('Collection', 'new_object_0_1')
        self.create_object_in_collection('sub_collection_1', 'new_object_1_0')
        self.create_object_in_collection('sub_collection_1', 'new_object_1_1')

        self.remove_object_from_collection('Collection', 'new_object_0_0')
        self.remove_object_from_collection('Collection', 'new_object_0_1')
        self.remove_object_from_collection('sub_collection_1', 'new_object_1_0')
        self.remove_object_from_collection('sub_collection_1', 'new_object_1_1')
        self.assertUserSuccess()

    def test_remove_collection_from_collection(self):
        self.create_collection_in_collection('Collection', 'plaf0')
        self.create_collection_in_collection('Collection', 'plaf1')
        self.remove_collection_from_collection('Collection', 'plaf0')
        self.remove_collection_from_collection('Collection', 'plaf1')

        self.remove_collection('plaf0')
        self.remove_collection('plaf1')

        self.create_collection_in_collection('Collection', 'plaf1')
        self.remove_collection_from_collection('Collection', 'plaf1')
        self.assertUserSuccess()

    def test_create_instance_in_collection_after_join(self):
        self.create_collection_in_collection('Collection', 'src')
        self.create_object_in_collection('src', 'new_object_0_0')
        self.create_collection_in_collection('Collection', 'dst')
        self.new_collection_instance('src', 'src_instance_in_Collection')
        self.new_collection_instance('src', 'src_instance_in_dst')
        self.link_object_to_collection('Collection', 'src_instance_in_Collection')
        self.link_object_to_collection('dst', 'src_instance_in_dst')
        self.assertUserSuccess()

    def test_create_instance_in_collection_before_join(self):
        # if collection instances are create before join we need to ensure that
        # the collection is received before the instance
        import time
        self._sender.disconnect_dccsync()
        self._receiver.disconnect_dccsync()
        time.sleep(1)
        self.create_collection_in_collection('Collection', 'src')
        self.create_object_in_collection('src', 'new_object_0_0')
        self.create_collection_in_collection('Collection', 'dst')
        self.new_collection_instance('src', 'src_instance_in_Collection')
        self.new_collection_instance('src', 'src_instance_in_dst')
        self.link_object_to_collection('Collection', 'src_instance_in_Collection')
        self.link_object_to_collection('dst', 'src_instance_in_dst')
        self._sender.connect_and_join_dccsync()
        self._receiver.connect_and_join_dccsync()
        self.assertUserSuccess()

    def test_rename_collection(self):
        self.create_collection_in_collection('Collection', 'old_name')
        self.create_object_in_collection('old_name', 'object_0')
        self.create_object_in_collection('old_name', 'object_1')
        self.create_collection_in_collection('old_name', 'collection_0_old')
        self.create_collection_in_collection('old_name', 'collection_1_old')
        self.create_object_in_collection('collection_0_old', 'object_0_0')

        self.rename_collection('collection_1_old', 'collection_1_new')
        self.rename_collection('old_name', 'new_name')
        self.rename_collection('collection_0_old', 'collection_0_new')
        self.assertUserSuccess()


if __name__ == '__main__':
    unittest.main()
