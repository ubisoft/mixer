import unittest
import testcase


def new_to_scene(name: str):
    import bpy
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)


def create_collection_in_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = bpy.data.collections.new(child_name)
    parent.children.link(child)


def remove_collection_from_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = parent.children[child_name]
    parent.children.unlink(child)


def create_object_in_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = bpy.data.objects.new(child_name, None)
    parent.objects.link(child)


def add_object_to_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = bpy.data.objects[child_name]
    parent.objects.link(child)


def remove_object_from_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = bpy.data.objects[child_name]
    parent.objects.unlink(child)


def remove_collection(name: str):
    import bpy
    c = bpy.data.collections[name]
    bpy.data.collections.remove(c)


def instanciate_collection(collection_name: str, instance_name: str):
    import bpy
    collection = bpy.data.collections[collection_name]
    instance = bpy.data.objects.new(name=instance_name, object_data=None)
    instance.instance_collection = collection
    instance.instance_type = 'COLLECTION'
    layer = bpy.context.view_layer
    layer.update()
    c = bpy.data.collections.new("__ploip__")
    bpy.data.collections.remove(c)


class CollectionTestCase(testcase.BlenderTestCase):
    def create_collection_in_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(create_collection_in_collection, parent_name, child_name)

    def remove_collection_from_collection(self, parent_name: str, child_name: str):
        self._sender.send_function(remove_collection_from_collection, parent_name, child_name)

    def remove_collection(self, collection_name: str):
        self._sender.send_function(remove_collection, collection_name)

    def create_object_in_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(create_object_in_collection, collection_name, object_name)

    def add_object_to_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(add_object_to_collection, collection_name, object_name)

    def remove_object_from_collection(self, collection_name: str, object_name: str):
        self._sender.send_function(remove_object_from_collection, collection_name, object_name)

    def instanciate_collection(self, collection_name: str, instance_name: str):
        self._sender.send_function(instanciate_collection, collection_name, instance_name)


class test_scene_collection_default_doc(CollectionTestCase):

    def test_scene_collection_create_FAILS(self):
        self._sender.send_function(new_to_scene, 'plop')
        self.assertUserSuccess()


class test_collection_default_doc(CollectionTestCase):

    def test_create_collection_in_collection(self):
        self.create_collection_in_collection('Collection', 'plop')
        self.create_collection_in_collection('Collection', 'plaf')
        self.create_collection_in_collection('plop', 'sous_plop')
        self.create_collection_in_collection('plaf', 'sous_plaf')
        self.assertUserSuccess()

    def test_create_collection_in_collection_FAILS(self):
        self.create_collection_in_collection('Collection', 'plop')
        self.create_collection_in_collection('Collection', 'plaf')
        # YES it fails in this order
        # it seems that sendSceneDataToServer handler does not notice the change
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


if __name__ == '__main__':
    unittest.main()
