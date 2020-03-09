from contextlib import contextmanager
import os
import sys
import subprocess
import shutil
import logging
import time
import json
import copy
from pathlib import Path
from datetime import datetime

import bpy
import socket
from mathutils import *
from . import clientBlender
from .broadcaster import common
from bpy.app.handlers import persistent
from bpy.types import UIList

from .shareData import shareData

from .data import get_dcc_sync_props
from .stats import StatsTimer, save_statistics, get_stats_filename

logger = logging.getLogger(__package__)


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
            shareData.client.sendMesh(obj)
            shareData.client.sendMeshConnection(obj)


def updateTransform(obj):
    shareData.client.sendTransform(obj)


def leave_current_room():
    shareData.currentRoom = None
    set_handlers(False)

    if None != shareData.current_statistics and shareData.auto_save_statistics:
        save_statistics(shareData.current_statistics, shareData.statistics_directory)
    shareData.current_statistics = None
    shareData.auto_save_statistics = False
    shareData.statistics_directory = None

    if shareData.client is not None:
        if bpy.app.timers.is_registered(shareData.client.networkConsumer):
            bpy.app.timers.unregister(shareData.client.networkConsumer)

        shareData.client.disconnect()
        del(shareData.client)
        shareData.client = None
    UpdateRoomListOperator.rooms_cached = False


@persistent
def onLoad(scene):
    connected = shareData.client is not None and shareData.client.isConnected()
    if connected:
        leave_current_room()


def updateSceneChanged():
    shareData.client.sendSetCurrentScene(bpy.context.scene.name_full)

    # send scene objects
    for obj in bpy.context.scene.objects:
        shareData.client.sendSceneObject(obj)

    # send scene collections
    for col in bpy.context.scene.collection.children:
        shareData.client.sendSceneCollection(col)

    shareData.client.currentSceneName = bpy.context.scene.name_full


class CollectionInfo:
    def __init__(self, hide_viewport, instance_offset, children, parent, objects=None):
        self.hide_viewport = hide_viewport
        self.instance_offset = instance_offset
        self.children = children
        self.parent = parent
        self.objects = objects or []


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
    for col in shareData.blenderCollections:
        if collectionName in col.children:
            return col
    return None


def updateCollectionsState():
    newCollectionsNames = set([bpy.context.scene.collection.name] + list(shareData.blenderCollections.keys()))
    oldCollectionsNames = set(shareData.collectionsInfo.keys())

    shareData.collectionsAdded = newCollectionsNames - oldCollectionsNames
    shareData.collectionsRemoved = oldCollectionsNames - newCollectionsNames

    shareData.collectionsAddedToCollection.clear()
    shareData.collectionsRemovedFromCollection.clear()
    for collectionName, collectionInfo in shareData.collectionsInfo.items():
        collection = getCollection(collectionName)
        if not collection:
            continue
        oldChildren = set(collectionInfo.children)
        newChildren = set([x.name_full for x in collection.children])

        for x in newChildren - oldChildren:
            shareData.collectionsAddedToCollection.add((getParentCollection(x).name_full, x))

        for x in oldChildren - newChildren:
            shareData.collectionsRemovedFromCollection.add((shareData.collectionsInfo[x].parent, x))

        newObjects = set([x.name_full for x in collection.objects])
        oldObjects = set([shareData.objectsRenamed.get(x, x) for x in collectionInfo.objects])

        addedObjects = [x for x in newObjects - oldObjects]
        if len(addedObjects) > 0:
            shareData.objectsAddedToCollection[collectionName] = addedObjects

        removedObjects = [x for x in oldObjects - newObjects]
        if len(removedObjects) > 0:
            shareData.objectsRemovedFromCollection[collectionName] = removedObjects


def updateCollectionsInfo():
    shareData.collectionsInfo = {}

    # Master Collection (scene dependent)
    collection = bpy.context.scene.collection
    children = [x.name_full for x in collection.children]
    shareData.collectionsInfo[collection.name_full] = CollectionInfo(
        collection.hide_viewport, collection.instance_offset, children, None, [x.name_full for x in collection.objects])
    for child in collection.children:
        shareData.collectionsInfo[child.name_full] = CollectionInfo(child.hide_viewport, child.instance_offset, [
                                                               x.name_full for x in child.children], collection.name_full)

    # All other collections (all scenes)
    for collection in shareData.blenderCollections.values():
        if not shareData.collectionsInfo.get(collection.name_full):
            shareData.collectionsInfo[collection.name_full] = CollectionInfo(collection.hide_viewport, collection.instance_offset, [
                                                                        x.name_full for x in collection.children], None)
        for child in collection.children:
            shareData.collectionsInfo[child.name_full] = CollectionInfo(child.hide_viewport, child.instance_offset, [
                                                                   x.name_full for x in child.children], collection.name_full)

    # Store collections objects (already done for master collection above)
    for collection in shareData.blenderCollections.values():
        shareData.collectionsInfo[collection.name_full].objects = [x.name_full for x in collection.objects]

def updateFrameChangedRelatedObjectsState(oldObjects : dict, newObjects : dict):
    for objName, matrix in shareData.objectsTransforms.items():
        newObj = shareData.oldObjects.get(objName)
        if not newObj:
            continue
        if newObj.matrix_local != matrix:
            shareData.objectsTransformed.add(objName)

def updateObjectsState(oldObjects : dict, newObjects : dict, stats_timer: StatsTimer):
    with stats_timer.child("checkObjectsAddedAndRemoved"):
        objects = set(newObjects.keys())
        shareData.objectsAdded = objects - oldObjects.keys()
        shareData.objectsRemoved = oldObjects.keys() - objects

    shareData.oldObjects = newObjects

    if len(shareData.objectsAdded) == 1 and len(shareData.objectsRemoved) == 1:
        shareData.objectsRenamed[list(shareData.objectsRemoved)[0]] = list(shareData.objectsAdded)[0]
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


def updateObjectsInfo():
    shareData.oldObjects = shareData.blenderObjects

    shareData.objectsTransforms = {}
    for obj in shareData.blenderObjects.values():
        shareData.objectsTransforms[obj.name_full] = obj.matrix_local.copy()

def updateCurrentData():
    updateCollectionsInfo()    
    updateObjectsInfo()    
    shareData.objectsVisibility = dict((x.name_full, x.hide_viewport) for x in shareData.blenderObjects.values())
    shareData.objectsParents = dict((x.name_full, x.parent.name_full if x.parent != None else "") for x in shareData.blenderObjects.values())

def isInObjectMode():
    return hasattr(bpy.context, "active_object") and (not bpy.context.active_object or bpy.context.active_object.mode == 'OBJECT')


def removeObjectsFromCollections():
    changed = False
    for collectionName in shareData.objectsRemovedFromCollection:
        objectNames = shareData.objectsRemovedFromCollection.get(collectionName)
        for objName in objectNames:
            shareData.client.sendRemoveObjectFromCollection(collectionName, objName)
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
            shareData.client.sendAddObjectToCollection(collectionName, objectName)
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
        if obj :
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
    with StatsTimer(shareData.current_statistics, "sendFrameChanged") as timer:
        with timer.child("setFrame"):
            shareData.client.sendFrame(scene.frame_current)

        with timer.child("clearLists"):
            shareData.clearChangedFrameRelatedLists()

        with timer.child("updateFrameChangedRelatedObjectsState"):            
            updateFrameChangedRelatedObjectsState(shareData.oldObjects, shareData.blenderObjects)

        with timer.child("checkForChangeAndSendUpdates"):
            updateObjectsTransforms()

        # update for next change
        with timer.child("updateObjectsInfo"):
            updateObjectsInfo()

@persistent
def sendSceneDataToServer(scene):
    logger.info("sendSceneDataToServer")
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
            updateCurrentData()
            updateSceneChanged()
            return

        if not isInObjectMode():
            return

        with timer.child("updateObjectsState") as child_timer:            
            updateObjectsState(shareData.oldObjects, shareData.blenderObjects, child_timer)

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
            updateCurrentData()


@persistent
def onUndoRedoPre(scene):
    shareData.setDirty()
    #shareData.selectedObjectsNames = set()
    # for obj in bpy.context.selected_objects:
    #    shareData.selectedObjectsNames.add(obj.name)
    if not isInObjectMode():
        return

    shareData.client.currentSceneName = bpy.context.scene.name_full

    shareData.clearLists()
    updateCurrentData()

def remapObjectsInfo():
    # update objects references
    addedObjects = set(shareData.blenderObjects.keys()) - set(shareData.oldObjects.keys())
    removedObjects = set(shareData.oldObjects.keys()) - set(shareData.blenderObjects.keys())
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

    oldObjectsName = dict([(k, None) for k in shareData.oldObjects.keys()])  # value not needed    
    remapObjectsInfo()
    for k, v in shareData.oldObjects.items():
        if k in oldObjectsName:
            oldObjectsName[k] = v

    with StatsTimer(shareData.current_statistics, "onUndoRedoPost") as timer:
        with timer.child("updateObjectsState") as child_timer:
            updateObjectsState(oldObjectsName, shareData.oldObjects, child_timer)

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


rooms_cache = None
getting_rooms = False


def updateListRoomsProperty():
    get_dcc_sync_props().rooms.clear()
    if rooms_cache:
        for room in rooms_cache:
            item = get_dcc_sync_props().rooms.add()
            item.name = room


def onRooms(rooms):
    global getting_rooms, rooms_cache
    if not "Local" in rooms:
        rooms_cache = ["Local"] + rooms
    else:
        rooms_cache = [] + rooms

    connected = shareData.roomListUpdateClient is not None and shareData.roomListUpdateClient.isConnected()
    if connected:
        if bpy.app.timers.is_registered(shareData.roomListUpdateClient.networkConsumer):
            bpy.app.timers.unregister(shareData.roomListUpdateClient.networkConsumer)
        shareData.roomListUpdateClient.disconnect()
        del(shareData.roomListUpdateClient)
        shareData.roomListUpdateClient = None

    updateListRoomsProperty()
    getting_rooms = False


def addLocalRoom():
    get_dcc_sync_props().rooms.clear()
    localItem = get_dcc_sync_props().rooms.add()
    localItem.name = "Local"
    UpdateRoomListOperator.rooms_cached = True


def getRooms(force=False):
    global getting_rooms, rooms_cache
    if getting_rooms:
        return

    if not force and rooms_cache:
        return

    host = get_dcc_sync_props().host
    port = get_dcc_sync_props().port
    shareData.roomListUpdateClient = None

    up = server_is_up(host, port)
    get_dcc_sync_props().remoteServerIsUp = up

    if up:
        shareData.roomListUpdateClient = clientBlender.ClientBlender(
            f"roomListUpdateClient {shareData.sessionId}", host, port)

    if not up or not shareData.roomListUpdateClient.isConnected():
        rooms_cache = ["Local"]
        return

    getting_rooms = True
    if not bpy.app.timers.is_registered(shareData.roomListUpdateClient.networkConsumer):
        bpy.app.timers.register(shareData.roomListUpdateClient.networkConsumer)

    shareData.roomListUpdateClient.addCallback('roomsList', onRooms)
    shareData.roomListUpdateClient.sendListRooms()


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
        shareData.client.sendAddObjectToCollection(collection.name_full, obj.name_full)

    for childCollection in collection.children:
        shareData.client.sendAddCollectionToCollection(collection.name_full, childCollection.name_full)


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

    shareData.client.sendFrame(bpy.context.scene.frame_current)


def set_handlers(connect: bool):
    try:
        if connect:
            shareData.depsgraph = bpy.context.evaluated_depsgraph_get()
            bpy.app.handlers.frame_change_post.append(sendFrameChanged)
            bpy.app.handlers.depsgraph_update_post.append(sendSceneDataToServer)
            bpy.app.handlers.undo_pre.append(onUndoRedoPre)
            bpy.app.handlers.redo_pre.append(onUndoRedoPre)
            bpy.app.handlers.undo_post.append(onUndoRedoPost)
            bpy.app.handlers.redo_post.append(onUndoRedoPost)
            bpy.app.handlers.load_post.append(onLoad)
        else:
            bpy.app.handlers.load_post.remove(onLoad)
            bpy.app.handlers.frame_change_post.remove(sendFrameChanged)
            bpy.app.handlers.depsgraph_update_post.remove(sendSceneDataToServer)
            bpy.app.handlers.undo_pre.remove(onUndoRedoPre)
            bpy.app.handlers.redo_pre.remove(onUndoRedoPre)
            bpy.app.handlers.undo_post.remove(onUndoRedoPost)
            bpy.app.handlers.redo_post.remove(onUndoRedoPost)
            shareData.depsgraph = None
    except:
        print("Error setting handlers")


def start_local_server():
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
    except:
        return False


def create_main_client(host: str, port: int, room: str):
    shareData.sessionId += 1
    shareData.client = clientBlender.ClientBlender(f"syncClient {shareData.sessionId}", host, port)
    shareData.client.addCallback('SendContent', send_scene_content)
    shareData.client.addCallback('ClearContent', clear_scene_content)
    if not shareData.client.isConnected():
        return {'CANCELLED'}
    if not bpy.app.timers.is_registered(shareData.client.networkConsumer):
        bpy.app.timers.register(shareData.client.networkConsumer)

    shareData.client.joinRoom(room)
    shareData.currentRoom = room
    shareData.current_statistics = {
        "session_id": shareData.sessionId,
        "blendfile": bpy.data.filepath,
        "statsfile": get_stats_filename(shareData.runId, shareData.sessionId),
        "user": os.getlogin(),
        "room": room,
        "children": {}
    }
    shareData.auto_save_statistics = get_dcc_sync_props().auto_save_statistics
    shareData.statistics_directory = get_dcc_sync_props().statistics_directory
    set_handlers(True)


class CreateRoomOperator(bpy.types.Operator):
    """Create a new room on DCC Sync server"""
    bl_idname = "dcc_sync.create_room"
    bl_label = "DCCSync Create Room"
    bl_options = {'REGISTER'}

    def execute(self, context):
        connected = shareData.client is not None and shareData.client.isConnected()
        if connected:
            set_handlers(False)

            if bpy.app.timers.is_registered(shareData.client.networkConsumer):
                bpy.app.timers.unregister(shareData.client.networkConsumer)

            if shareData.client is not None:
                shareData.client.disconnect()
                del(shareData.client)
                shareData.client = None
        else:
            shareData.isLocal = False
            room = get_dcc_sync_props().room
            host = get_dcc_sync_props().host
            port = get_dcc_sync_props().port

            create_main_client(host, port, room)

            UpdateRoomListOperator.rooms_cached = False
        return {'FINISHED'}


class JoinOrLeaveRoomOperator(bpy.types.Operator):
    """Join a room, or leave the one that was already joined"""
    bl_idname = "dcc_sync.join_or_leave_room"
    bl_label = "DCCSync Join or Leave Room"
    bl_options = {'REGISTER'}

    def execute(self, context):
        global rooms_cache

        shareData.currentRoom = None
        connected = shareData.client is not None and shareData.client.isConnected()
        if connected:
            leave_current_room()
        else:
            shareData.setDirty()
            updateCurrentData()

            shareData.isLocal = False
            try:
                roomIndex = get_dcc_sync_props().room_index
                room = get_dcc_sync_props().rooms[roomIndex].name
            except IndexError:
                room = "Local"

            localServerIsUp = True
            if room == 'Local':
                host = common.DEFAULT_HOST
                port = common.DEFAULT_PORT
                localServerIsUp = server_is_up(host, port)
                # Launch local server? if it doesn't exist
                if not localServerIsUp:
                    start_local_server()
                shareData.isLocal = True
            else:
                host = get_dcc_sync_props().host
                port = get_dcc_sync_props().port

            create_main_client(host, port, room)

        return {'FINISHED'}


class UpdateRoomListOperator(bpy.types.Operator):
    """Fetch and update the list of DCC Sync rooms"""
    bl_idname = "dcc_sync.update_room_list"
    bl_label = "DCCSync Update Room List"
    bl_options = {'REGISTER'}

    def execute(self, context):
        logger.info("UpdateRoomListOperator")
        getRooms(force=True)
        updateListRoomsProperty()
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
            except:
                print('materials not found')

            updateParams(obj)
            updateTransform(obj)

        return {'FINISHED'}


class LaunchVRtistOperator(bpy.types.Operator):
    """Launch a VRtist instance"""
    bl_idname = "vrtist.launch"
    bl_label = "Launch VRtist"
    bl_options = {'REGISTER'}

    def execute(self, context):
        dcc_sync_props = get_dcc_sync_props()
        room = shareData.currentRoom
        if not room:
            bpy.ops.dcc_sync.join_or_leave_room()
            room = shareData.currentRoom

        hostname = "localhost"
        if not shareData.isLocal:
            hostname = dcc_sync_props.host
        args = [dcc_sync_props.VRtist, "--room", room, "--hostname", hostname, "--port", str(dcc_sync_props.port)]
        subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        return {'FINISHED'}


class WriteStatisticsOperator(bpy.types.Operator):
    """Write dccsync statistics in a file"""
    bl_idname = "dcc_sync.write_statistics"
    bl_label = "DCCSync Write Statistics"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if None != shareData.current_statistics:
            save_statistics(shareData.current_statistics, get_dcc_sync_props().statistics_directory)
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
    UpdateRoomListOperator,
    SendSelectionOperator,
    JoinOrLeaveRoomOperator,
    WriteStatisticsOperator,
    OpenStatsDirOperator
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
