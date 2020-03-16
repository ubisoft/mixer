import unittest
import testcase


def new_to_scene(name: str):
    import bpy
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)


def new_to_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = bpy.data.collections.new(child_name)
    parent.children.link(child)


def remove_from_collection(parent_name: str, child_name: str):
    import bpy
    parent = bpy.data.collections[parent_name]
    child = parent.children[child_name]
    parent.children.unlink(child)


def remove_collection(name: str):
    import bpy
    c = bpy.data.collections[name]
    bpy.data.collections.remove(c)


class test_collection_default_doc(testcase.BlenderTestCase):
    def test_create_collection_in_collection(self):
        self._sender.send_function(new_to_collection, 'Collection', 'plop')
        self._sender.send_function(new_to_collection, 'Collection', 'plaf')
        self._sender.send_function(new_to_collection, 'plop', 'sous_plop')
        self._sender.send_function(new_to_collection, 'plaf', 'sous_plaf')

    def test_create_collection_in_collection_FAILS(self):
        self._sender.send_function(new_to_collection, 'Collection', 'plop')
        self._sender.send_function(new_to_collection, 'Collection', 'plaf')
        # YES it fails in this order
        # it seems that sendSceneDataToServer handler does not notice the change
        self._sender.send_function(new_to_collection, 'plaf', 'sous_plaf')
        self._sender.send_function(new_to_collection, 'plop', 'sous_plop')

    def test_create_collection_in_collection_name_clash(self):
        self._sender.send_function(new_to_collection, 'Collection', 'plop')
        self._sender.send_function(new_to_collection, 'Collection', 'Collection')
        self._sender.send_function(new_to_collection, 'plop', 'plop')

    def test_remove_collection(self):
        # TODO
        self._sender.send_function(new_to_collection, 'Collection', 'plaf0')
        self._sender.send_function(new_to_collection, 'Collection', 'plaf1')
        self._sender.send_function(remove_from_collection, 'Collection', 'plaf0')
        self._sender.send_function(remove_from_collection, 'Collection', 'plaf1')

        self._sender.send_function(remove_collection, 'plaf0')
        self._sender.send_function(remove_collection, 'plaf1')

        self._sender.send_function(new_to_collection, 'Collection', 'plaf1')
        self._sender.send_function(remove_from_collection, 'Collection', 'plaf1')

    def test_create_scene_collection(self):
        self._sender.send_function(new_to_scene, 'plop')


if __name__ == '__main__':
    unittest.main()
