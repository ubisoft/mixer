import logging
import bpy

from mixer.broadcaster import common
from mixer.broadcaster.client import Client
from mixer.share_data import share_data

logger = logging.getLogger(__name__)


def send_scene(client: Client, scene_name: str):
    logger.info("send_scene %s", scene_name)
    buffer = common.encode_string(scene_name)
    client.add_command(common.Command(common.MessageType.SCENE, buffer, 0))


def delete_scene(scene):
    # Due to bug mentionned here https://developer.blender.org/T71422, deleting a scene with D.scenes.remove()
    # in a function called from a timer gives a hard crash. This is due to context.window being None.
    # To overcome this issue, we call an operator with a custom context that define window.
    # https://devtalk.blender.org/t/new-timers-have-no-context-object-why-is-that-so-cant-override-it/6802
    def window():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    return window

    ctx = {"window": window(), "scene": scene}
    bpy.ops.scene.delete(ctx)


def build_scene(data):
    scene_name, _ = common.decode_string(data, 0)
    logger.info("build_scene %s", scene_name)

    # remove what was previously the last scene that could not be removed
    to_remove = None
    if len(bpy.data.scenes) == 1 and bpy.data.scenes[0].name == "__last_scene_to_be_removed__":
        to_remove = bpy.data.scenes[0]

    scene = share_data.blender_scenes.get(scene_name)
    if scene is None:
        scene = bpy.data.scenes.new(scene_name)
        share_data.blender_scenes[scene_name] = scene

    if to_remove is not None:
        delete_scene(to_remove)


def send_scene_removed(client: Client, scene_name: str):
    logger.info("send_scene_removed %s", scene_name)
    buffer = common.encode_string(scene_name)
    client.add_command(common.Command(common.MessageType.SCENE_REMOVED, buffer, 0))


def build_scene_removed(data):
    scene_name, _ = common.decode_string(data, 0)
    logger.info("build_scene_removed %s", scene_name)
    scene = share_data.blender_scenes.get(scene_name)
    delete_scene(scene)
    share_data.blender_scenes_dirty = True


def send_scene_renamed(client: Client, old_name: str, new_name: str):
    logger.info("send_scene_renamed %s to %s", old_name, new_name)
    buffer = common.encode_string(old_name) + common.encode_string(new_name)
    client.add_command(common.Command(common.MessageType.SCENE_RENAMED, buffer, 0))


def build_scene_renamed(data):
    old_name, index = common.decode_string(data, 0)
    new_name, _ = common.decode_string(data, index)
    logger.info("build_scene_renamed %s to %s", old_name, new_name)
    scene = share_data.blender_scenes.get(old_name)
    scene.name = new_name
    share_data.blender_scenes_dirty = True


def send_add_collection_to_scene(client: Client, scene_name: str, collection_name: str):
    logger.info("send_add_collection_to_scene %s <- %s", scene_name, collection_name)

    buffer = common.encode_string(scene_name) + common.encode_string(collection_name)
    client.add_command(common.Command(common.MessageType.ADD_COLLECTION_TO_SCENE, buffer, 0))


def build_collection_to_scene(data):
    scene_name, index = common.decode_string(data, 0)
    collection_name, _ = common.decode_string(data, index)
    logger.info("build_collection_to_scene %s <- %s", scene_name, collection_name)

    scene = share_data.blender_scenes[scene_name]
    collection = share_data.blender_collections[collection_name]
    scene.collection.children.link(collection)

    share_data.update_collection_temporary_visibility(collection_name)


def send_remove_collection_from_scene(client: Client, scene_name: str, collection_name: str):
    logger.info("send_remove_collection_from_scene %s <- %s", scene_name, collection_name)

    buffer = common.encode_string(scene_name) + common.encode_string(collection_name)
    client.add_command(common.Command(common.MessageType.REMOVE_COLLECTION_FROM_SCENE, buffer, 0))


def build_remove_collection_from_scene(data):
    scene_name, index = common.decode_string(data, 0)
    collection_name, _ = common.decode_string(data, index)
    logger.info("build_remove_collection_from_scene %s <- %s", scene_name, collection_name)
    scene = share_data.blender_scenes[scene_name]
    collection = share_data.blender_collections[collection_name]
    scene.collection.children.unlink(collection)


def send_add_object_to_vrtist(client: Client, scene_name: str, obj_name: str):
    logger.debug("send_add_object_to_vrtist %s <- %s", scene_name, obj_name)
    buffer = common.encode_string(scene_name) + common.encode_string(obj_name)
    client.add_command(common.Command(common.MessageType.ADD_OBJECT_TO_VRTIST, buffer, 0))


def send_add_object_to_scene(client: Client, scene_name: str, obj_name: str):
    logger.info("send_add_object_to_scene %s <- %s", scene_name, obj_name)
    buffer = common.encode_string(scene_name) + common.encode_string(obj_name)
    client.add_command(common.Command(common.MessageType.ADD_OBJECT_TO_SCENE, buffer, 0))


def build_add_object_to_scene(data):
    scene_name, index = common.decode_string(data, 0)
    object_name, _ = common.decode_string(data, index)
    logger.info("build_add_object_to_scene %s <- %s", scene_name, object_name)

    scene = share_data.blender_scenes[scene_name]
    # We may have received an object creation message before this collection link message
    # and object creation will have created and linked the collecetion if needed
    if scene.collection.objects.get(object_name) is None:
        object_ = share_data.blender_objects[object_name]
        scene.collection.objects.link(object_)


def send_remove_object_from_scene(client: Client, scene_name: str, object_name: str):
    logger.info("send_remove_object_from_scene %s <- %s", scene_name, object_name)
    buffer = common.encode_string(scene_name) + common.encode_string(object_name)
    client.add_command(common.Command(common.MessageType.REMOVE_OBJECT_FROM_SCENE, buffer, 0))


def build_remove_object_from_scene(data):
    scene_name, index = common.decode_string(data, 0)
    object_name, _ = common.decode_string(data, index)
    logger.info("build_remove_object_from_scene %s <- %s", scene_name, object_name)
    scene = share_data.blender_scenes[scene_name]
    object_ = share_data.blender_objects[object_name]
    scene.collection.objects.unlink(object_)
