import unittest
import testcase
from pathlib import Path
import blender_lib as bl


class CollectionTestCase(testcase.BlenderTestCase):
    def create_collection_in_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.create_collection_in_collection, parent_name, child_name)

    def remove_collection_from_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(bl.remove_collection_from_collection, parent_name, child_name)

    def remove_collection(self, collection_name: str):
        self._sender.send_function(bl.remove_collection, collection_name)

    def rename_collection(self, old_name: str, new_name: str):
        self._sender.send_function(bl.rename_collection, old_name, new_name)

    def create_object_in_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.create_object_in_collection, collection_name, object_name)

    def add_object_to_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.add_object_to_collection, collection_name, object_name)

    def remove_object_from_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(bl.remove_object_from_collection, collection_name, object_name)

    def instanciate_collection(self, collection_name: str, instance_name: str):
        self._sender.send_function(bl.instanciate_collection, collection_name, instance_name)


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
        # TODO
        self.create_collection_in_collection('Collection', 'plaf0')
        self.create_collection_in_collection('Collection', 'plaf1')
        self.remove_collection_from_collection('Collection', 'plaf0')
        self.remove_collection_from_collection('Collection', 'plaf1')

        self.remove_collection('plaf0')
        self.remove_collection('plaf1')

        self.create_collection_in_collection('Collection', 'plaf1')
        self.remove_collection_from_collection('Collection', 'plaf1')
        self.assertUserSuccess()

    def test_create_collection_instance(self):
        self.create_collection_in_collection('Collection', 'src')
        self.create_object_in_collection('src', 'new_object_0_0')
        self.create_object_in_collection('src', 'new_object_0_1')
        self.create_collection_in_collection('Collection', 'dst')
        self.instanciate_collection('src', 'instance_0')
        self.instanciate_collection('src', 'instance_1')
        self.add_object_to_collection('dst', 'instance_0')
        self.add_object_to_collection('dst', 'instance_1')
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
