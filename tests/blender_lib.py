"""
Functions to be remotely executed in Blender via python_server.py

Remote execution relies on source code extractiona and transmission to the
execution sever, so each function must contain its imports
"""


def open(path: str):
    import bpy

    bpy.ops.wm.open_mainfile(filepath=path)


def save(path: str):
    import bpy

    bpy.ops.wm.save_as_mainfile(filepath=path)


def quit():
    import bpy

    bpy.ops.wm.quit_blender()


# Collections


def new_collection(name: str):
    import bpy

    bpy.data.collections.new(name)


def link_collection_to_collection(parent_name: str, child_name: str):
    import bpy

    parent = bpy.data.collections[parent_name]
    child = bpy.data.collections[child_name]
    parent.children.link(child)


def create_collection_in_collection(parent_name: str, child_name: str):
    """
    Works even with a name clash (actual collection name is not child_name)
    """
    import bpy

    parent = bpy.data.collections[parent_name]
    child = bpy.data.collections.new(child_name)
    parent.children.link(child)


def unlink_collection_from_collection(parent_name: str, child_name: str):
    import bpy

    parent = bpy.data.collections[parent_name]
    child = parent.children[child_name]
    parent.children.unlink(child)


def create_object_in_collection(parent_name: str, child_name: str):
    import bpy

    parent = bpy.data.collections[parent_name]
    child = bpy.data.objects.new(child_name, None)
    parent.objects.link(child)


def link_object_to_collection(parent_name: str, child_name: str):
    import bpy

    parent = bpy.data.collections[parent_name]
    child = bpy.data.objects[child_name]
    parent.objects.link(child)


def unlink_object_from_collection(parent_name: str, child_name: str):
    import bpy

    parent = bpy.data.collections[parent_name]
    child = bpy.data.objects[child_name]
    parent.objects.unlink(child)


def remove_collection(name: str):
    import bpy

    c = bpy.data.collections[name]
    bpy.data.collections.remove(c)


def rename_collection(old_name: str, new_name: str):
    import bpy

    c = bpy.data.collections[old_name]
    c.name = new_name


def new_collection_instance(collection_name: str, instance_name: str):
    import bpy

    collection = bpy.data.collections[collection_name]
    instance = bpy.data.objects.new(name=instance_name, object_data=None)
    instance.instance_collection = collection
    instance.instance_type = "COLLECTION"


#
# Scenes
#


def new_scene(name: str):
    import bpy

    bpy.data.scenes.new(name)


def remove_scene(name: str):
    import bpy

    s = bpy.data.scenes[name]
    bpy.data.scenes.remove(s)


def link_collection_to_scene(scene_name: str, collection_name: str):
    import bpy

    master_collection = bpy.data.scenes[scene_name].collection
    collection = bpy.data.collections[collection_name]
    master_collection.children.link(collection)


def unlink_collection_from_scene(scene_name: str, collection_name: str):
    import bpy

    master_collection = bpy.data.scenes[scene_name].collection
    collection = bpy.data.collections[collection_name]
    master_collection.children.unlink(collection)


def link_object_to_scene(scene_name: str, object_name: str):
    import bpy

    master_collection = bpy.data.scenes[scene_name].collection
    object_ = bpy.data.objects[object_name]
    master_collection.objects.link(object_)


def new_object(name: str):
    import bpy

    bpy.data.objects.new(name, None)


def unlink_object_from_scene(scene_name: str, object_name: str):
    import bpy

    master_collection = bpy.data.scenes[scene_name].collection
    object_ = bpy.data.objects[object_name]
    master_collection.objects.unlink(object_)


def rename_scene(old_name: str, new_name: str):
    import bpy

    scene = bpy.data.scenes[old_name]
    scene.name = new_name


#
# object
#


def rename_object(old_name: str, new_name: str):
    import bpy

    obj = bpy.data.objects[old_name]
    obj.name = new_name


#
# misc
#


def rename_mesh(old_name: str, new_name: str):
    import bpy

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name == old_name:
            obj.name = new_name


def add(radius=1.0, type="EMPTY", location=(0.0, 0.0, 0.0)):
    import bpy

    bpy.ops.object.add(radius=radius, type=type, location=location)
