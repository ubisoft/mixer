import logging
import os
import socket
import subprocess
import time

from pathlib import Path
from typing import Mapping

import bpy
from bpy.app.handlers import persistent

from .shareData import ShareData, shareData
from .blender_client import scene as scene_lib

from . import clientBlender
from . import ui
from .data import get_dcc_sync_props
from .stats import StatsTimer, save_statistics, get_stats_filename, stats_timer

logger = logging.getLogger(__package__)
logger.setLevel(logging.INFO)


class TransformStruct:
    def __init__(self, translate, quaternion, scale, visible):
        self.translate = translate
        self.quaternion = quaternion
        self.scale = scale
        self.visible = visible


def updateParams(obj):
    # send collection instances
    if obj.instance_type == 'COLLECTION':
        shareData.client.sendCollectionInstance(obj)
        return

    if not hasattr(obj, "data"):
        return

    typename = obj.bl_rna.name
    if obj.data:
        typename = obj.data.bl_rna.name

    if typename != 'Camera' and typename != 'Mesh' and typename != 'Curve'and typename != 'Text Curve' and typename != 'Sun Light' and typename != 'Point Light' and typename != 'Spot Light' and typename != 'Grease Pencil':
        return

    if typename == 'Camera':
        shareData.client.sendCamera(obj)

    if typename == 'Sun Light' or typename == 'Point Light' or typename == 'Spot Light':
        shareData.client.sendLight(obj)

    if typename == 'Grease Pencil':
        for material in obj.data.materials:
            shareData.client.sendMaterial(material)
        shareData.client.sendGreasePencilMesh(obj)
        shareData.client.sendGreasePencilConnection(obj)

    if typename == 'Mesh' or typename == 'Curve' or typename == 'Text Curve':
        if obj.mode == 'OBJECT':
            shareData.client.sendMesh(obj)


def updateTransform(obj):
    shareData.client.sendTransform(obj)


def join_room(room_name: str):
    assert shareData.currentRoom is None
    user = get_dcc_sync_props().user
    shareData.sessionId += 1
    shareData.currentRoom = room_name
    shareData.client.joinRoom(room_name)
    shareData.client.setClientName(user)
    shareData.client.sendSetCurrentScene(bpy.context.scene.name_full)

    shareData.current_statistics = {
        "session_id": shareData.sessionId,
        "blendfile": bpy.data.filepath,
        "statsfile": get_stats_filename(shareData.runId, shareData.sessionId),
        "user": user,
        "room": room_name,
        "children": {}
    }
    shareData.auto_save_statistics = get_dcc_sync_props().auto_save_statistics
    shareData.statistics_directory = get_dcc_sync_props().statistics_directory
    # join a room <==> want to track local changes
    set_handlers(True)


def leave_current_room():
    # room ==> client
    assert not shareData.currentRoom or shareData.client
    if shareData.currentRoom:
        if shareData.client:
            shareData.client.leaveRoom(shareData.currentRoom)
        shareData.currentRoom = None
        set_handlers(False)

    shareData.clearBeforeState()

    if shareData.current_statistics is not None and shareData.auto_save_statistics:
        save_statistics(shareData.current_statistics,
                        shareData.statistics_directory)
    shareData.current_statistics = None
    shareData.auto_save_statistics = False
    shareData.statistics_directory = None


def is_joined():
    connected = shareData.client is not None and shareData.client.isConnected()
    return connected and shareData.currentRoom


@persistent
def onLoad(scene):
    disconnect()


def getScene(sceneName):
    return shareData.blenderScenes.get(sceneName)


def getCollection(collectionName):
    """
    May only return a non master collection
    """
    return shareData.blenderCollections.get(collectionName)


def getParentCollection(collectionName):
    """
    May return a master or non master collection
    """
    for scene in bpy.data.scenes:
        if collectionName in scene.collection.children:
            return scene.collection
    for col in shareData.blenderCollections.values():
        if collectionName in col.children:
            return col
    return None


def updateScenesState():
    """
    Must be called before updateCollectionsState so that non empty collections added to master
    collection are processed
    """
    newNames = shareData.blenderScenes.keys()
    oldNames = shareData.scenesInfo.keys()

    shareData.scenesAdded |= newNames - oldNames
    shareData.scenesRemoved |= oldNames - newNames

    # walk the old scenes
    for sceneName, sceneInfo in shareData.scenesInfo.items():
        scene = getScene(sceneName)
        if not scene:
            continue
        sceneName = scene.name_full
        oldChildren = set(sceneInfo.children)
        newChildren = set([x.name_full for x in scene.collection.children])

        for x in newChildren - oldChildren:
            shareData.collectionsAddedToScene.add((sceneName, x))

        for x in oldChildren - newChildren:
            shareData.collectionsRemovedFromScene.add((sceneName, x))

        oldObjects = {shareData.objectsRenamed.get(x, x) for x in sceneInfo.objects}
        newObjects = {x.name_full for x in scene.collection.objects}

        addedObjects = list(newObjects - oldObjects)
        if len(addedObjects) > 0:
            shareData.objectsAddedToScene[sceneName] = addedObjects

        removedObjects = list(oldObjects - newObjects)
        if len(removedObjects) > 0:
            shareData.objectsRemovedFromScene[sceneName] = removedObjects

    # now the new scenes (in case of rename)
    for sceneName in shareData.scenesAdded:
        scene = getScene(sceneName)
        if not scene:
            continue
        newChildren = {x.name_full for x in scene.collection.children}
        for x in newChildren:
            shareData.collectionsAddedToScene.add((sceneName, x))

        addedObjects = set([x.name_full for x in scene.collection.objects])
        if len(addedObjects) > 0:
            shareData.objectsAddedToScene[sceneName] = addedObjects


def updateCollectionsState():
    """
    Update non master collection state
    """
    newCollectionsNames = shareData.blenderCollections.keys()
    oldCollectionsNames = shareData.collectionsInfo.keys()

    shareData.collectionsAdded |= newCollectionsNames - oldCollectionsNames
    shareData.collectionsRemoved |= oldCollectionsNames - newCollectionsNames

    # walk the old collections
    for collectionName, collectionInfo in shareData.collectionsInfo.items():
        collection = getCollection(collectionName)
        if not collection:
            continue
        oldChildren = set(collectionInfo.children)
        newChildren = set([x.name_full for x in collection.children])

        for x in newChildren - oldChildren:
            parent = getParentCollection(x)
            if parent is not None:
                shareData.collectionsAddedToCollection.add((parent.name_full, x))
            else:
                logger.warning('UpdateCollectionState(): Collection not found or has no parent "%s"', x)

        for x in oldChildren - newChildren:
            shareData.collectionsRemovedFromCollection.add(
                (shareData.collectionsInfo[x].parent, x))

        newObjects = set([x.name_full for x in collection.objects])
        oldObjects = set([shareData.objectsRenamed.get(x, x)
                          for x in collectionInfo.objects])

        addedObjects = [x for x in newObjects - oldObjects]
        if len(addedObjects) > 0:
            shareData.objectsAddedToCollection[collectionName] = addedObjects

        removedObjects = [x for x in oldObjects - newObjects]
        if len(removedObjects) > 0:
            shareData.objectsRemovedFromCollection[collectionName] = removedObjects

    # now the new collections (in case of rename)
    for collectionName in shareData.collectionsAdded:
        collection = getCollection(collectionName)
        if not collection:
            continue
        newChildren = set([x.name_full for x in collection.children])
        for x in newChildren:
            parent = getParentCollection(x)
            if parent is not None:
                shareData.collectionsAddedToCollection.add((parent.name_full, x))
            else:
                logger.warning('UpdateCollectionState(): Collection not found or has no parent "%s"', x)

        addedObjects = set([x.name_full for x in collection.objects])
        if len(addedObjects) > 0:
            shareData.objectsAddedToCollection[collectionName] = addedObjects


def updateFrameChangedRelatedObjectsState(oldObjects: dict, newObjects: dict):
    for objName, matrix in shareData.objectsTransforms.items():
        newObj = shareData.oldObjects.get(objName)
        if not newObj:
            continue
        if newObj.matrix_local != matrix:
            shareData.objectsTransformed.add(objName)


@stats_timer(shareData)
def updateObjectsState(oldObjects: dict, newObjects: dict):
    stats_timer = shareData.current_stats_timer

    with stats_timer.child("checkObjectsAddedAndRemoved"):
        objects = set(newObjects.keys())
        shareData.objectsAdded = objects - oldObjects.keys()
        shareData.objectsRemoved = oldObjects.keys() - objects

    shareData.oldObjects = newObjects

    if len(shareData.objectsAdded) == 1 and len(shareData.objectsRemoved) == 1:
        shareData.objectsRenamed[list(shareData.objectsRemoved)[
            0]] = list(shareData.objectsAdded)[0]
        shareData.objectsAdded.clear()
        shareData.objectsRemoved.clear()
        return

    for objName in shareData.objectsRemoved:
        if objName in shareData.oldObjects:
            del shareData.oldObjects[objName]

    with stats_timer.child("updateObjectsParentingChanged"):
        for objName, parent in shareData.objectsParents.items():
            if objName not in shareData.oldObjects:
                continue
            newObj = shareData.oldObjects[objName]
            newObjParent = "" if newObj.parent is None else newObj.parent.name_full
            if newObjParent != parent:
                shareData.objectsReparented.add(objName)

    with stats_timer.child("updateObjectsVisibilityChanged"):
        for objName, visible in shareData.objectsVisibility.items():
            newObj = shareData.oldObjects.get(objName)
            if not newObj:
                continue
            if visible != newObj.hide_viewport:
                shareData.objectsVisibilityChanged.add(objName)

    updateFrameChangedRelatedObjectsState(oldObjects, newObjects)


def isInObjectMode():
    return not hasattr(bpy.context, "active_object") or (not bpy.context.active_object or bpy.context.active_object.mode == 'OBJECT')


def removeObjectsFromScenes():
    changed = False
    for scene_name, object_names in shareData.objectsRemovedFromScene.items():
        for object_name in object_names:
            scene_lib.sendRemoveObjectFromScene(shareData.client, scene_name, object_name)
            changed = True
    return changed


def removeObjectsFromCollections():
    """
    Non master collections, actually
    """
    changed = False
    for collection_name, object_names in shareData.objectsRemovedFromCollection.items():
        for object_name in object_names:
            shareData.client.sendRemoveObjectFromCollection(collection_name, object_name)
            changed = True
    return changed


def removeCollectionsFromScenes():
    changed = False
    for scene_name, collection_name in shareData.collectionsRemovedFromScene:
        scene_lib.sendRemoveCollectionFromScene(shareData.client, scene_name, collection_name)
        changed = True
    return changed


def removeCollectionsFromCollections():
    """
    Non master collections, actually
    """
    changed = False
    for parent_name, child_name in shareData.collectionsRemovedFromCollection:
        shareData.client.sendRemoveCollectionFromCollection(parent_name, child_name)
        changed = True
    return changed


def addScenes():
    changed = False
    for scene in shareData.scenesAdded:
        scene_lib.sendScene(shareData.client, scene)
        changed = True
    return changed


def removeScenes():
    changed = False
    for scene in shareData.scenesRemoved:
        scene_lib.sendSceneRemoved(shareData.client, scene)
        changed = True
    return changed


def removeCollections():
    changed = False
    for collection in shareData.collectionsRemoved:
        shareData.client.sendCollectionRemoved(collection)
        changed = True
    return changed


def addObjects():
    changed = False
    for objName in shareData.objectsAdded:
        if objName in bpy.data.objects:
            obj = bpy.data.objects[objName]
            updateParams(obj)
            updateTransform(obj)
            changed = True
    return changed


def addCollections():
    changed = False
    for item in shareData.collectionsAdded:
        shareData.client.sendCollection(getCollection(item))
        changed = True
    return changed


def addCollectionsToCollections():
    changed = False
    for parent_name, child_name in shareData.collectionsAddedToCollection:
        shareData.client.sendAddCollectionToCollection(parent_name, child_name)
        changed = True
    return changed


def addCollectionsToScenes():
    changed = False
    for scene_name, collection_name in shareData.collectionsAddedToScene:
        scene_lib.sendAddCollectionToScene(shareData.client, scene_name, collection_name)
        changed = True
    return changed


def addObjectsToCollections():
    changed = False
    for collectionName, objectNames in shareData.objectsAddedToCollection.items():
        for objectName in objectNames:
            shareData.client.sendAddObjectToCollection(
                collectionName, objectName)
            changed = True
    return changed


def addObjectsToScenes():
    changed = False
    for sceneName, objectNames in shareData.objectsAddedToScene.items():
        for objectName in objectNames:
            scene_lib.sendAddObjectToScene(shareData.client, sceneName, objectName)
            changed = True
    return changed


def updateCollectionsParameters():
    changed = False
    for collection in shareData.blenderCollections.values():
        info = shareData.collectionsInfo.get(collection.name_full)
        if info:
            if info.hide_viewport != collection.hide_viewport or info.instance_offset != collection.instance_offset:
                shareData.client.sendCollection(collection)
                changed = True
    return changed


def deleteSceneObjects():
    changed = False
    for objName in shareData.objectsRemoved:
        shareData.client.sendDeletedObject(objName)
        changed = True
    return changed


def renameObjects():
    changed = False
    for oldName, newName in shareData.objectsRenamed.items():
        shareData.client.sendRenamedObjects(oldName, newName)
        changed = True
    return changed


def updateObjectsVisibility():
    changed = False
    for objName in shareData.objectsVisibilityChanged:
        if objName in shareData.blenderObjects:
            updateTransform(shareData.blenderObjects[objName])
            changed = True
    return changed


def updateObjectsTransforms():
    changed = False
    for objName in shareData.objectsTransformed:
        if objName in shareData.blenderObjects:
            updateTransform(shareData.blenderObjects[objName])
            changed = True
    return changed


def reparentObjects():
    changed = False
    for objName in shareData.objectsReparented:
        obj = shareData.blenderObjects.get(objName)
        if obj:
            updateTransform(obj)
            changed = True
    return changed


def updateObjectsData():
    if len(shareData.depsgraph.updates) == 0:
        return  # Exit here to avoid noise if you want to put breakpoints in this function

    dataContainer = {}
    data = set()
    transforms = set()

    for update in shareData.depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name

        if typename == 'Object':
            if hasattr(obj, 'data'):
                if obj.data in dataContainer:
                    dataContainer[obj.data].append(obj)
                else:
                    dataContainer[obj.data] = [obj]
            transforms.add(obj)

        if typename == 'Camera' or typename == 'Mesh' or typename == 'Curve' or typename == 'Text Curve' or typename == 'Sun Light' or typename == 'Point Light' or typename == 'Spot Light' or typename == 'Grease Pencil':
            data.add(obj)

        if typename == 'Material':
            shareData.client.sendMaterial(obj)

    # Send transforms
    for obj in transforms:
        updateTransform(obj)

    # Send data (mesh) of objects
    for d in data:
        container = dataContainer.get(d)
        if not container:
            continue
        for c in container:
            updateParams(c)


@persistent
def sendFrameChanged(scene):
    logger.info("sendFrameChanged")
    if not shareData.client:
        return

    with StatsTimer(shareData, "sendFrameChanged") as timer:
        with timer.child("setFrame"):
            shareData.client.sendFrame(scene.frame_current)

        with timer.child("clearLists"):
            shareData.clearChangedFrameRelatedLists()

        with timer.child("updateFrameChangedRelatedObjectsState"):
            updateFrameChangedRelatedObjectsState(
                shareData.oldObjects, shareData.blenderObjects)

        with timer.child("checkForChangeAndSendUpdates"):
            updateObjectsTransforms()

        # update for next change
        with timer.child("updateObjectsInfo"):
            shareData.updateObjectsInfo()


@stats_timer(shareData)
@persistent
def sendSceneDataToServer(scene, dummy):
    timer = shareData.current_stats_timer

    logger.info("sendSceneDataToServer")
    if not shareData.client:
        return

    shareData.setDirty()
    with timer.child("clearLists"):
        shareData.clearLists()

    # prevent processing self events
    if shareData.client.receivedCommandsProcessed:
        if not shareData.client.blockSignals:
            shareData.client.receivedCommandsProcessed = False
        return

    if not isInObjectMode():
        return

    updateObjectsState(shareData.oldObjects,
                       shareData.blenderObjects)

    with timer.child("updateScenesState"):
        updateScenesState()

    with timer.child("updateCollectionsState"):
        updateCollectionsState()

    changed = False
    with timer.child("checkForChangeAndSendUpdates"):
        changed |= removeObjectsFromCollections()
        changed |= removeObjectsFromScenes()
        changed |= removeCollectionsFromCollections()
        changed |= removeCollectionsFromScenes()
        changed |= removeCollections()
        changed |= removeScenes()
        changed |= addObjects()
        changed |= addCollections()
        changed |= addScenes()
        changed |= addCollectionsToScenes()
        changed |= addCollectionsToCollections()
        changed |= addObjectsToCollections()
        changed |= addObjectsToScenes()
        changed |= updateCollectionsParameters()
        changed |= deleteSceneObjects()
        changed |= renameObjects()
        changed |= updateObjectsVisibility()
        changed |= updateObjectsTransforms()
        changed |= reparentObjects()

    if not changed:
        with timer.child("updateObjectsData"):
            shareData.depsgraph = bpy.context.evaluated_depsgraph_get()
            updateObjectsData()

    # update for next change
    with timer.child("updateCurrentData"):
        shareData.updateCurrentData()


@persistent
def onUndoRedoPre(scene):
    shareData.setDirty()
    # shareData.selectedObjectsNames = set()
    # for obj in bpy.context.selected_objects:
    #    shareData.selectedObjectsNames.add(obj.name)
    if not isInObjectMode():
        return

    shareData.clearLists()
    shareData.updateCurrentData()


def remapObjectsInfo():
    # update objects references
    addedObjects = set(shareData.blenderObjects.keys()) - \
        set(shareData.oldObjects.keys())
    removedObjects = set(shareData.oldObjects.keys()) - \
        set(shareData.blenderObjects.keys())
    # we are only able to manage one object rename
    if len(addedObjects) == 1 and len(removedObjects) == 1:
        oldName = list(removedObjects)[0]
        newName = list(addedObjects)[0]

        visible = shareData.objectsVisibility[oldName]
        del shareData.objectsVisibility[oldName]
        shareData.objectsVisibility[newName] = visible

        parent = shareData.objectsParents[oldName]
        del shareData.objectsParents[oldName]
        shareData.objectsParents[newName] = parent
        for name, parent in shareData.objectsParents.items():
            if parent == oldName:
                shareData.objectsParents[name] = newName

        matrix = shareData.objectsTransforms[oldName]
        del shareData.objectsTransforms[oldName]
        shareData.objectsTransforms[newName] = matrix

    shareData.oldObjects = shareData.blenderObjects


@stats_timer(shareData)
@persistent
def onUndoRedoPost(scene, dummy):
    shareData.setDirty()
    # apply only in object mode
    if not isInObjectMode():
        return

    oldObjectsName = dict(
        [(k, None) for k in shareData.oldObjects.keys()])  # value not needed
    remapObjectsInfo()
    for k, v in shareData.oldObjects.items():
        if k in oldObjectsName:
            oldObjectsName[k] = v

    with StatsTimer(shareData, "updateObjectsState") as child_timer:
        updateObjectsState(
            oldObjectsName, shareData.oldObjects, child_timer)

    updateCollectionsState()
    updateScenesState()

    removeObjectsFromScenes()
    removeObjectsFromCollections()
    removeCollectionsFromScenes()
    removeCollectionsFromCollections()

    removeCollections()
    removeScenes()
    addScenes()
    addObjects()
    addCollections()
    addCollectionsToCollections()
    addObjectsToCollections()
    updateCollectionsParameters()
    deleteSceneObjects()
    renameObjects()
    updateObjectsVisibility()
    updateObjectsTransforms()
    reparentObjects()

    # send selection content (including data)
    materials = set()
    for obj in bpy.context.selected_objects:
        updateTransform(obj)
        if hasattr(obj, "data"):
            updateParams(obj)
        if hasattr(obj, "material_slots"):
            for slot in obj.material_slots[:]:
                materials.add(slot.material)

    for material in materials:
        shareData.client.sendMaterial(material)

    shareData.depsgraph = bpy.context.evaluated_depsgraph_get()


def updateListUsers(client_ids: Mapping[str, str] = None):
    shareData.client_ids = client_ids


def clear_scene_content():
    set_handlers(False)

    collections = []
    objs = []
    for collection in bpy.data.collections:
        collections.append(collection)
        for obj in collection.objects:
            if obj.type == 'MESH' or obj.type == 'LIGHT' or obj.type == 'CAMERA':
                objs.append(obj)

    for obj in objs:
        bpy.data.objects.remove(obj, do_unlink=True)

    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)

    for block in bpy.data.textures:
        if block.users == 0:
            bpy.data.textures.remove(block)

    for block in bpy.data.images:
        if block.users == 0:
            bpy.data.images.remove(block)

    for collection in collections:
        bpy.data.collections.remove(collection)

    set_handlers(True)


def isParentInCollection(collection, obj):
    parent = obj.parent
    while parent is not None:
        if parent in collection.objects[:]:
            return True
        parent = parent.parent
    return False


def send_scene_content():
    if get_dcc_sync_props().no_send_scene_content:
        return

    shareData.clearBeforeState()
    sendSceneDataToServer(None, None)

    shareData.client.sendFrameStartEnd(
        bpy.context.scene.frame_start, bpy.context.scene.frame_end)
    shareData.client.sendFrame(bpy.context.scene.frame_current)


def set_handlers(connect: bool):
    try:
        if connect:
            shareData.depsgraph = bpy.context.evaluated_depsgraph_get()
            bpy.app.handlers.frame_change_post.append(sendFrameChanged)
            bpy.app.handlers.depsgraph_update_post.append(
                sendSceneDataToServer)
            bpy.app.handlers.undo_pre.append(onUndoRedoPre)
            bpy.app.handlers.redo_pre.append(onUndoRedoPre)
            bpy.app.handlers.undo_post.append(onUndoRedoPost)
            bpy.app.handlers.redo_post.append(onUndoRedoPost)
            bpy.app.handlers.load_post.append(onLoad)
        else:
            bpy.app.handlers.load_post.remove(onLoad)
            bpy.app.handlers.frame_change_post.remove(sendFrameChanged)
            bpy.app.handlers.depsgraph_update_post.remove(
                sendSceneDataToServer)
            bpy.app.handlers.undo_pre.remove(onUndoRedoPre)
            bpy.app.handlers.redo_pre.remove(onUndoRedoPre)
            bpy.app.handlers.undo_post.remove(onUndoRedoPost)
            bpy.app.handlers.redo_post.remove(onUndoRedoPost)
            shareData.depsgraph = None
    except Exception as e:
        logger.error("Exception during set_handlers(%s) : %s", connect, e)


def wait_for_server(host, port):
    attempts = 0
    max_attempts = 10
    while not server_is_up(host, port) and attempts < max_attempts:
        attempts += 1
        time.sleep(0.2)
    return attempts < max_attempts


def start_local_server(wait_for_server=False):
    dir_path = Path(__file__).parent
    serverPath = dir_path / 'broadcaster' / 'dccBroadcaster.py'

    if get_dcc_sync_props().showServerConsole:
        args = {'creationflags': subprocess.CREATE_NEW_CONSOLE}
    else:
        args = {}

    shareData.localServerProcess = subprocess.Popen([bpy.app.binary_path_python, str(
        serverPath)], shell=False, **args)


def server_is_up(address, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((address, port))
        s.shutdown(socket.SHUT_RDWR)
        s.close()
        return True
    except Exception:
        return False


def is_localhost(host):
    # does not catch local address
    return host == "localhost" or host == "127.0.0.1"


def connect():
    props = get_dcc_sync_props()
    if not server_is_up(props.host, props.port):
        if is_localhost(props.host):
            start_local_server(wait_for_server=True)
            wait_for_server(props.host, props.port)

    if not isClientConnected():
        if not create_main_client(props.host, props.port):
            return False

    shareData.client.setClientName(props.user)
    return True


def disconnect():
    leave_current_room()

    # the socket has already been disconnected
    if shareData.client is not None:
        if shareData.client.isConnected():
            shareData.client.disconnect()
        shareData.client_ids = None
        shareData.client = None
    shareData.currentRoom = None


def isClientConnected():
    return shareData.client is not None and shareData.client.isConnected()


def create_main_client(host: str, port: int):
    assert shareData.client is None
    client = clientBlender.ClientBlender(
        f"syncClient {shareData.sessionId}", host, port)
    client.connect()
    if not client.isConnected():
        return False

    shareData.client = client
    shareData.client.addCallback('SendContent', send_scene_content)
    shareData.client.addCallback('ClearContent', clear_scene_content)
    if not bpy.app.timers.is_registered(shareData.client.networkConsumer):
        bpy.app.timers.register(shareData.client.networkConsumer)

    return True


class CreateRoomOperator(bpy.types.Operator):
    """Create a new room on DCC Sync server"""
    bl_idname = "dcc_sync.create_room"
    bl_label = "DCCSync Create Room"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        props = get_dcc_sync_props()
        return not shareData.currentRoom and bool(props.room)

    def execute(self, context):
        assert not shareData.currentRoom
        shareData.currentRoom = None
        if not connect():
            return {'CANCELLED'}

        props = get_dcc_sync_props()
        join_room(props.room)
        return {'FINISHED'}


class JoinRoomOperator(bpy.types.Operator):
    """Join a room"""
    bl_idname = "dcc_sync.join_room"
    bl_label = "DCCSync Join Room"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        roomIndex = get_dcc_sync_props().room_index
        return isClientConnected() and roomIndex < len(get_dcc_sync_props().rooms)

    def execute(self, context):
        assert not shareData.currentRoom
        shareData.setDirty()
        shareData.currentRoom = None

        if not connect():
            self.report({'ERROR'})

        shareData.isLocal = False
        props = get_dcc_sync_props()
        roomIndex = props.room_index
        room = props.rooms[roomIndex].name
        join_room(room)
        return {'FINISHED'}


class LeaveRoomOperator(bpy.types.Operator):
    """Reave the current room"""
    bl_idname = "dcc_sync.leave_room"
    bl_label = "DCCSync Leave Room"
    bl_options = {'REGISTER'}

    def execute(self, context):
        leave_current_room()
        ui.update_ui_lists()
        return {'FINISHED'}


class ConnectOperator(bpy.types.Operator):
    """Connect to the DCCSync server"""
    bl_idname = "dcc_sync.connect"
    bl_label = "Connect to server"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = get_dcc_sync_props()
        try:
            self.report(
                {'INFO'}, f'Connecting to "{props.host}:{props.port}" ...')
            ok = connect()
            if not ok:
                self.report({'ERROR'}, "unknown error")
                return {'CANCELLED'}
            else:
                self.report(
                    {'INFO'}, f'Connected to "{props.host}:{props.port}" ...')
        except socket.gaierror:
            msg = f'Cannot connect to "{props.host}": invalid host name or address'
            self.report({'ERROR'}, msg)
        except Exception as e:
            self.report({'ERROR'}, repr(e))
            return {'CANCELLED'}

        return {'FINISHED'}


class DisconnectOperator(bpy.types.Operator):
    """Disconnect from the DccSync server"""
    bl_idname = "dcc_sync.disconnect"
    bl_label = "Disconnect from server"
    bl_options = {'REGISTER'}

    def execute(self, context):
        disconnect()
        ui.update_ui_lists()
        ui.redraw()
        return {'FINISHED'}


class SendSelectionOperator(bpy.types.Operator):
    """Send current selection to DCC Sync server"""
    bl_idname = "dcc_sync.send_selection"
    bl_label = "DCCSync Send selection"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if shareData.client is None:
            return {'CANCELLED'}

        selectedObjects = bpy.context.selected_objects
        for obj in selectedObjects:
            try:
                for slot in obj.material_slots[:]:
                    shareData.client.sendMaterial(slot.material)
            except Exception:
                print('materials not found')

            updateParams(obj)
            updateTransform(obj)

        return {'FINISHED'}


class LaunchVRtistOperator(bpy.types.Operator):
    """Launch a VRtist instance"""
    bl_idname = "vrtist.launch"
    bl_label = "Launch VRtist"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        dcc_sync_props = get_dcc_sync_props()
        if not shareData.currentRoom:
            if not connect():
                return {'CANCELLED'}

            props = get_dcc_sync_props()
            join_room(props.room)

        hostname = "localhost"
        if not shareData.isLocal:
            hostname = dcc_sync_props.host
        args = [dcc_sync_props.VRtist, "--room", shareData.currentRoom,
                "--hostname", hostname, "--port", str(dcc_sync_props.port)]
        subprocess.Popen(args, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, shell=False)
        return {'FINISHED'}


class WriteStatisticsOperator(bpy.types.Operator):
    """Write dccsync statistics in a file"""
    bl_idname = "dcc_sync.write_statistics"
    bl_label = "DCCSync Write Statistics"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if shareData.current_statistics is not None:
            save_statistics(shareData.current_statistics,
                            get_dcc_sync_props().statistics_directory)
        return {'FINISHED'}


class OpenStatsDirOperator(bpy.types.Operator):
    """Write dccsync stats directory in explorer"""
    bl_idname = "dcc_sync.open_stats_dir"
    bl_label = "DCCSync Open Stats Directory"
    bl_options = {'REGISTER'}

    def execute(self, context):
        os.startfile(get_dcc_sync_props().statistics_directory)
        return {'FINISHED'}


classes = (
    LaunchVRtistOperator,
    CreateRoomOperator,
    ConnectOperator,
    DisconnectOperator,
    SendSelectionOperator,
    JoinRoomOperator,
    LeaveRoomOperator,
    WriteStatisticsOperator,
    OpenStatsDirOperator,
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
