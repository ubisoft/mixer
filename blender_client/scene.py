from ..broadcaster import common
from ..shareData import shareData
import logging
import bpy

logger = logging.getLogger(__name__)


def sendScene(client: 'ClientBlender', scene_name: str):
    logger.debug("sendScene %s", scene_name)
    buffer = common.encodeString(scene_name)
    client.addCommand(common.Command(
        common.MessageType.SCENE, buffer, 0))


def delete_scene(scene):
    # https://devtalk.blender.org/t/new-timers-have-no-context-object-why-is-that-so-cant-override-it/6802
    def window():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    return window

    ctx = {'window': window(), 'scene': scene}
    bpy.ops.scene.delete(ctx)


def buildScene(data):
    scene_name, _ = common.decodeString(data, 0)
    logger.debug("buildScene %s", scene_name)

    # remove what was previously the last scene that could not be removed
    to_remove = None
    if len(bpy.data.scenes) == 1 and bpy.data.scenes[0].name == '__last_scene_to_be_removed__':
        to_remove = bpy.data.scenes[0]

    scene = shareData.blenderScenes.get(scene_name)
    if scene is None:
        scene = bpy.data.scenes.new(scene_name)
        shareData.blenderScenes[scene_name] = scene

    if to_remove is not None:
        delete_scene(to_remove)


def sendSceneRemoved(client: 'ClientBlender', scene_name: str):
    logger.debug("sendSceneRemoved %s", scene_name)
    buffer = common.encodeString(scene_name)
    client.addCommand(common.Command(
        common.MessageType.SCENE_REMOVED, buffer, 0))


def buildSceneRemoved(data):
    scene_name, _ = common.decodeString(data, 0)
    logger.debug("buildSceneRemoved %s", scene_name)
    scene = shareData.blenderScenes.get(scene_name)
    delete_scene(scene)
    shareData.blenderScenesDirty = True


def sendSceneRenamed(client: 'ClientBlender', old_name: str, new_name: str):
    logger.debug("sendSceneRenamed %s to %s", old_name, new_name)
    buffer = common.encodeString(old_name) + common.encodeString(new_name)
    client.addCommand(common.Command(
        common.MessageType.SCENE_RENAMED, buffer, 0))


def buildSceneRenamed(data):
    old_name, index = common.decodeString(data, 0)
    new_name, _ = common.decodeString(data, index)
    logger.debug("buildSceneRenamed %s to %s", old_name, new_name)
    scene = shareData.blenderScenes.get(old_name)
    scene.name = new_name
    shareData.blenderScenesDirty = True


def sendAddCollectionToScene(client: 'ClientBlender', scene_name: str, collection_name: str):
    logger.debug("sendAddCollectionToScene %s <- %s", scene_name, collection_name)

    buffer = common.encodeString(scene_name) + common.encodeString(collection_name)
    client.addCommand(common.Command(
        common.MessageType.ADD_COLLECTION_TO_SCENE, buffer, 0))


def buildCollectionToScene(data):
    scene_name, index = common.decodeString(data, 0)
    collection_name, _ = common.decodeString(data, index)
    logger.debug("buildCollectionToScene %s <- %s", scene_name, collection_name)

    scene = shareData.blenderScenes[scene_name]
    collection = shareData.blenderCollections[collection_name]
    scene.collection.children.link(collection)


def sendRemoveCollectionFromScene(client: 'ClientBlender', scene_name: str, collection_name: str):
    logger.debug("sendRemoveCollectionFromScene %s <- %s", scene_name, collection_name)

    buffer = common.encodeString(scene_name) + common.encodeString(collection_name)
    client.addCommand(common.Command(
        common.MessageType.REMOVE_COLLECTION_FROM_SCENE, buffer, 0))


def buildRemoveCollectionFromScene(data):
    scene_name, index = common.decodeString(data, 0)
    collection_name, _ = common.decodeString(data, index)
    logger.debug("buildRemoveCollectionFromScene %s <- %s", scene_name, collection_name)
    scene = shareData.blenderScenes[scene_name]
    collection = shareData.blenderCollections[collection_name]
    scene.collection.children.unlink(collection)


def sendAddObjectToVRtist(client: 'ClientBlender', sceneName: str, objName: str):
    logger.debug("sendAddObjectToVRtist %s <- %s", sceneName, objName)
    buffer = common.encodeString(
        sceneName) + common.encodeString(objName)
    client.addCommand(common.Command(
        common.MessageType.ADD_OBJECT_TO_VRTIST, buffer, 0))


def sendAddObjectToScene(client: 'ClientBlender', sceneName: str, objName: str):
    logger.debug("sendAddObjectToScene %s <- %s", sceneName, objName)
    buffer = common.encodeString(
        sceneName) + common.encodeString(objName)
    client.addCommand(common.Command(
        common.MessageType.ADD_OBJECT_TO_SCENE, buffer, 0))


def buildAddObjectToScene(data):
    scene_name, index = common.decodeString(data, 0)
    object_name, _ = common.decodeString(data, index)
    logger.debug("buildAddObjectToScene %s <- %s", scene_name, object_name)

    scene = shareData.blenderScenes[scene_name]
    # We may have received an object creation message before this collection link message
    # and object creation will have created and linked the collecetion if needed
    if scene.collection.objects.get(object_name) is None:
        object_ = shareData.blenderObjects[object_name]
        scene.collection.objects.link(object_)


def sendRemoveObjectFromScene(client: 'ClientBlender', scene_name: str, object_name: str):
    logger.debug("sendRemoveObjectFromScene %s <- %s", scene_name, object_name)
    buffer = common.encodeString(scene_name) + common.encodeString(object_name)
    client.addCommand(common.Command(
        common.MessageType.REMOVE_OBJECT_FROM_SCENE, buffer, 0))


def buildRemoveObjectFromScene(data):
    scene_name, index = common.decodeString(data, 0)
    object_name, _ = common.decodeString(data, index)
    logger.debug("buildRemoveObjectFromScene %s <- %s", scene_name, object_name)
    scene = shareData.blenderScenes[scene_name]
    object_ = shareData.blenderObjects[object_name]
    scene.collection.objects.unlink(object_)
