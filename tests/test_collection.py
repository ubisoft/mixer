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


class Test_collection_Default_Doc(testcase.BlenderTestCase):
    def test_create_collection_in_collection(self):
        self._sender.send_function(new_to_collection, 'Collection', 'plop')
        self._sender.send_function(new_to_collection, 'Collection', 'plaf')
        self._sender.send_function(new_to_collection, 'plaf', 'sub')

    def test_create_scene_collection(self):
        self._sender.send_function(new_to_scene, 'plop')


if __name__ == '__main__':
    unittest.main()
