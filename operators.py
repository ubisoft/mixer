import asyncio
from contextlib import contextmanager
import subprocess
import logging
import time
from typing import Mapping
import json
import copy
from pathlib import Path
from datetime import datetime

import bpy
import socket
from . import clientBlender
from . import ui
from .shareData import shareData
from bpy.app.handlers import persistent

from .shareData import shareData

from .data import get_dcc_sync_props
from .stats import StatsTimer, save_statistics, get_stats_filename

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

    if typename != 'Camera' and typename != 'Mesh' and typename != 'Sun Light' and typename != 'Point Light' and typename != 'Spot Light' and typename != 'Grease Pencil':
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

    if typename == 'Mesh':
        if obj.mode == 'OBJECT':
            for material in obj.data.materials:
                shareData.client.sendMaterial(material)
            shareData.client.sendMesh(obj)
            shareData.client.sendMeshConnection(obj)


def updateTransform(obj):
    shareData.client.sendTransform(obj)


def join_room(room_name: str):
    assert shareData.currentRoom is None
    user = get_dcc_sync_props().user
    shareData.currentRoom = room_name
    shareData.client.joinRoom(room_name)
    shareData.client.setClientName(user)

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

    if None != shareData.current_statistics and shareData.auto_save_statistics:
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


def updateSceneChanged():
    shareData.client.sendSetCurrentScene(bpy.context.scene.name_full)

    # send scene objects
    for obj in bpy.context.scene.objects:
        shareData.client.sendSceneObject(obj)

    # send scene collections
    for col in bpy.context.scene.collection.children:
        shareData.client.sendSceneCollection(col)

    shareData.client.currentSceneName = bpy.context.scene.name_full


def getCollection(collectionName):
    collection = shareData.blenderCollections.get(collectionName)
    if collection:
        return collection
    if bpy.context.scene.collection.name_full == collectionName:
        return bpy.context.scene.collection
    return None


def getParentCollection(collectionName):
    if collectionName in bpy.context.scene.collection.children:
        return bpy.context.scene.collection
    for col in shareData.blenderCollections.values():
        if collectionName in col.children:
            return col
    return None


def updateCollectionsState():
    newCollectionsNames = set(
        [bpy.context.scene.collection.name] + list(shareData.blenderCollections.keys()))
    oldCollectionsNames = set(shareData.collectionsInfo.keys())

    shareData.collectionsAdded = newCollectionsNames - oldCollectionsNames
    shareData.collectionsRemoved = oldCollectionsNames - newCollectionsNames

    shareData.collectionsAddedToCollection.clear()
    shareData.collectionsRemovedFromCollection.clear()
    for collectionName, shareData.collectionInfo in shareData.collectionsInfo.items():
        collection = getCollection(collectionName)
        if not collection:
            continue
        oldChildren = set(shareData.collectionInfo.children)
        newChildren = set([x.name_full for x in collection.children])

        for x in newChildren - oldChildren:
            shareData.collectionsAddedToCollection.add(
                (getParentCollection(x).name_full, x))

        for x in oldChildren - newChildren:
            shareData.collectionsRemovedFromCollection.add(
                (shareData.collectionsInfo[x].parent, x))

        newObjects = set([x.name_full for x in collection.objects])
        oldObjects = set([shareData.objectsRenamed.get(x, x)
                          for x in shareData.collectionInfo.objects])

        addedObjects = [x for x in newObjects - oldObjects]
        if len(addedObjects) > 0:
            shareData.objectsAddedToCollection[collectionName] = addedObjects

        removedObjects = [x for x in oldObjects - newObjects]
        if len(removedObjects) > 0:
            shareData.objectsRemovedFromCollection[collectionName] = removedObjects


def updateFrameChangedRelatedObjectsState(oldObjects: dict, newObjects: dict):
    for objName, matrix in shareData.objectsTransforms.items():
        newObj = shareData.oldObjects.get(objName)
        if not newObj:
            continue
        if newObj.matrix_local != matrix:
            shareData.objectsTransformed.add(objName)


def updateObjectsState(oldObjects: dict, newObjects: dict, stats_timer: StatsTimer):
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
            if not objName in shareData.oldObjects:
                continue
            newObj = shareData.oldObjects[objName]
            newObjParent = "" if newObj.parent == None else newObj.parent.name_full
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
    return hasattr(bpy.context, "active_object") and (not bpy.context.active_object or bpy.context.active_object.mode == 'OBJECT')


def removeObjectsFromCollections():
    changed = False
    for collectionName in shareData.objectsRemovedFromCollection:
        objectNames = shareData.objectsRemovedFromCollection.get(
            collectionName)
        for objName in objectNames:
            shareData.client.sendRemoveObjectFromCollection(
                collectionName, objName)
            changed = True
    return changed


def removeCollectionsFromCollections():
    changed = False
    for item in shareData.collectionsRemovedFromCollection:
        shareData.client.sendRemoveCollectionFromCollection(item[0], item[1])
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
        if objName in bpy.context.scene.objects:
            obj = bpy.context.scene.objects[objName]
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
    for item in shareData.collectionsAddedToCollection:
        shareData.client.sendAddCollectionToCollection(item[0], item[1])
        changed = True
    return changed


def addObjectsToCollections():
    changed = False
    for collectionName in shareData.objectsAddedToCollection:
        objectNames = shareData.objectsAddedToCollection.get(collectionName)
        for objectName in objectNames:
            shareData.client.sendAddObjectToCollection(
                collectionName, objectName)
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


def createSceneObjects():
    changed = False
    for objName in shareData.objectsAdded:
        if objName in bpy.context.scene.objects:
            obj = bpy.context.scene.objects[objName]
            shareData.client.sendSceneObject(obj)
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
    container = {}
    data = set()
    transforms = set()

    for update in shareData.depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name

        if typename == 'Object':
            if hasattr(obj, 'data'):
                container[obj.data] = obj
            transforms.add(obj)

        if typename == 'Camera' or typename == 'Mesh' or typename == 'Sun Light' or typename == 'Point Light' or typename == 'Spot Light' or typename == 'Grease Pencil':
            data.add(obj)

        if typename == 'Material':
            shareData.client.sendMaterial(obj)

    # Send transforms
    for obj in transforms:
        updateTransform(obj)

    # Send data (mesh) of objects
    for d in data:
        if d in container:
            updateParams(container[d])


@persistent
def sendFrameChanged(scene):
    if not shareData.client:
        return

    with StatsTimer(shareData.current_statistics, "sendFrameChanged") as timer:
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


@persistent
def sendSceneDataToServer(scene):
    logger.info("sendSceneDataToServer")
    if not shareData.client:
        return

    shareData.setDirty()
    with StatsTimer(shareData.current_statistics, "sendSceneDataToServer") as timer:
        with timer.child("clearLists"):
            shareData.clearLists()

        # prevent processing self events
        if shareData.client.receivedCommandsProcessed:
            if not shareData.client.blockSignals:
                shareData.client.receivedCommandsProcessed = False
            return

        if shareData.client.currentSceneName != bpy.context.scene.name_full:
            shareData.updateCurrentData()
            updateSceneChanged()
            return

        if not isInObjectMode():
            return

        with timer.child("updateObjectsState") as child_timer:
            updateObjectsState(shareData.oldObjects,
                               shareData.blenderObjects, child_timer)

        with timer.child("updateCollectionsState"):
            updateCollectionsState()

        changed = False
        with timer.child("checkForChangeAndSendUpdates"):
            changed |= removeObjectsFromCollections()
            changed |= removeCollectionsFromCollections()
            changed |= removeCollections()
            changed |= addObjects()
            changed |= addCollections()
            changed |= addCollectionsToCollections()
            changed |= addObjectsToCollections()
            changed |= updateCollectionsParameters()
            changed |= createSceneObjects()
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

    shareData.client.currentSceneName = bpy.context.scene.name_full

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


@persistent
def onUndoRedoPost(scene):
    shareData.setDirty()
    # apply only in object mode
    if not isInObjectMode():
        return

    if shareData.client.currentSceneName != bpy.context.scene.name_full:
        updateSceneChanged()
        return

    oldObjectsName = dict(
        [(k, None) for k in shareData.oldObjects.keys()])  # value not needed
    remapObjectsInfo()
    for k, v in shareData.oldObjects.items():
        if k in oldObjectsName:
            oldObjectsName[k] = v

    with StatsTimer(shareData.current_statistics, "onUndoRedoPost") as timer:
        with timer.child("updateObjectsState") as child_timer:
            updateObjectsState(
                oldObjectsName, shareData.oldObjects, child_timer)

    updateCollectionsState()

    removeObjectsFromCollections()
    removeCollectionsFromCollections()
    removeCollections()
    addObjects()
    addCollections()
    addCollectionsToCollections()
    addObjectsToCollections()
    updateCollectionsParameters()
    createSceneObjects()
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


def send_collection_content(collection):
    for obj in collection.objects:
        shareData.client.sendAddObjectToCollection(
            collection.name_full, obj.name_full)

    for childCollection in collection.children:
        shareData.client.sendAddCollectionToCollection(
            collection.name_full, childCollection.name_full)


def send_collections():
    for collection in shareData.blenderCollections.values():
        shareData.client.sendCollection(collection)
        send_collection_content(collection)


def send_scene_content():
    if get_dcc_sync_props().no_send_scene_content:
        return

    with StatsTimer(shareData.current_statistics, "send_scene_content", True) as stats_timer:
        shareData.setDirty()
        shareData.client.currentSceneName = bpy.context.scene.name_full

        # First step : Send all Blender data (materials, objects, collection) existing in file
        # ====================================================================================

        with stats_timer.child("sendAllMaterials"):
            for material in bpy.data.materials:
                shareData.client.sendMaterial(material)

        with stats_timer.child("sendAllObjects"):
            for obj in bpy.data.objects:
                updateParams(obj)
                updateTransform(obj)

        # send all collections
        with stats_timer.child("sendAllCollections"):
            send_collections()

        # Second step : send current scene content
        # ========================================
        with stats_timer.child("sendSetCurrentScene"):
            shareData.client.sendSetCurrentScene(bpy.context.scene.name_full)

        with stats_timer.child("sendSceneObjects"):
            for obj in bpy.context.scene.objects:
                shareData.client.sendSceneObject(obj)

        with stats_timer.child("sendSceneCollections"):
            for col in bpy.context.scene.collection.children:
                shareData.client.sendSceneCollection(col)

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
        #args = {'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT}
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
    shareData.sessionId += 1
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
    def poll(self, context):
        roomIndex = get_dcc_sync_props().room_index
        return isClientConnected() and roomIndex < len(get_dcc_sync_props().rooms)

    def execute(self, context):
        assert not shareData.currentRoom
        shareData.setDirty()
        shareData.updateCurrentData()
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
        #props = get_dcc_sync_props()
        # return not shareData.currentRoom and bool(props.room)

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
        if None != shareData.current_statistics:
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


timer = None


class AsyncioLoopOperator(bpy.types.Operator):
    """
    Executes an asyncio loop, bluntly copied from
    From https://blenderartists.org/t/running-background-jobs-with-asyncio/673805

    Used by the unit tests (python_server.py)
    """
    bl_idname = "dcc_sync.asyncio_loop"
    bl_label = "Test Remote"
    command: bpy.props.EnumProperty(name="Command",
                                    description="Command being issued to the asyncio loop",
                                    default='TOGGLE', items=[
                                         ('START', "Start", "Start the loop"),
                                         ('STOP', "Stop", "Stop the loop"),
                                         ('TOGGLE', "Toggle", "Toggle the loop state")
                                    ])
    period: bpy.props.FloatProperty(name="Period",
                                    description="Time between two asyncio beats",
                                    default=0.01, subtype="UNSIGNED", unit="TIME")

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, event):
        global timer
        wm = context.window_manager
        if timer and self.command in ('STOP', 'TOGGLE'):
            wm.event_timer_remove(timer)
            timer = None
            return {'FINISHED'}
        elif not timer and self.command in ('START', 'TOGGLE'):
            wm.modal_handler_add(self)
            timer = wm.event_timer_add(self.period, window=context.window)
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}

    def modal(self, context, event):
        global timer
        if not timer:
            return {'FINISHED'}
        elif event.type != 'TIMER':
            return {'PASS_THROUGH'}
        else:
            loop = asyncio.get_event_loop()
            loop.stop()
            loop.run_forever()
            return {'RUNNING_MODAL'}


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
    AsyncioLoopOperator
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
