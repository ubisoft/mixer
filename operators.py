import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path

import bpy
import socket
from mathutils import *
from . import clientBlender
from .broadcaster import common
from bpy.app.handlers import persistent
from bpy.types import UIList

from .data import get_dcc_sync_props

logger = logging.getLogger(__package__)


class TransformStruct:
    def __init__(self, translate, quaternion, scale, visible):
        self.translate = translate
        self.quaternion = quaternion
        self.scale = scale
        self.visible = visible


class ShareData:
    def __init__(self):
        self.sessionId = 0  # For logging and debug
        self.client = None
        self.currentRoom = None
        self.isLocal = False
        self.localServerProcess = None
        self.selectedObjectsNames = []
        self.depsgraph = None
        self.roomListUpdateClient = None

        self.objectsAdded = set()
        self.objectsRemoved = set()
        self.collectionsAdded = set()
        self.collectionsRemoved = set()
        self.objectsAddedToCollection = {}
        self.objectsRemovedFromCollection = {}
        self.collectionsAddedToCollection = set()
        self.collectionsRemovedFromCollection = set()
        self.collectionsInfo = {}
        self.objectsReparented = set()
        self.objectsParents = {}
        self.objectsRenamed = {}
        self.objectsTransformed = set()
        self.objectsTransforms = {}
        self.objectsVisibilityChanged = set()
        self.objectsVisibility = {}
        self.objects = set()

    def clearLists(self):
        self.objectsAddedToCollection.clear()
        self.objectsRemovedFromCollection.clear()
        self.objectsReparented.clear()
        self.objectsRenamed.clear()
        self.objectsTransformed.clear()
        self.objectsVisibilityChanged.clear()


shareData = ShareData()


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
    shareData.client.sendSetCurrentScene(bpy.context.scene.name)

    # send scene objects
    for obj in bpy.context.scene.objects:
        shareData.client.sendSceneObject(obj)

    # send scene collections
    for col in bpy.context.scene.collection.children:
        shareData.client.sendSceneCollection(col)

    shareData.client.currentSceneName = bpy.context.scene.name


class CollectionInfo:
    def __init__(self, hide_viewport, instance_offset, children, parent, objects=None):
        self.hide_viewport = hide_viewport
        self.instance_offset = instance_offset
        self.children = children
        self.parent = parent
        self.objects = objects or []


def getCollection(collectionName):
    if collectionName in bpy.data.collections:
        return bpy.data.collections[collectionName]
    if bpy.context.scene.collection.name == collectionName:
        return bpy.context.scene.collection
    return None


def getParentCollection(collectionName):
    if collectionName in bpy.context.scene.collection.children:
        return bpy.context.scene.collection
    for col in bpy.data.collections:
        if collectionName in col.children:
            return col
    return None


def updateCollectionsState():
    newCollectionsNames = set([bpy.context.scene.collection.name] + [x.name for x in bpy.data.collections])
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
        newChildren = set([x.name for x in collection.children])

        for x in newChildren - oldChildren:
            shareData.collectionsAddedToCollection.add((getParentCollection(x).name, x))

        for x in oldChildren - newChildren:
            shareData.collectionsRemovedFromCollection.add((shareData.collectionsInfo[x].parent, x))

        newObjects = set([x.name for x in collection.objects])
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
    children = [x.name for x in collection.children]
    shareData.collectionsInfo[collection.name] = CollectionInfo(
        collection.hide_viewport, collection.instance_offset, children, None, [x.name for x in collection.objects])
    for child in collection.children:
        shareData.collectionsInfo[child.name] = CollectionInfo(child.hide_viewport, child.instance_offset, [
                                                               x.name for x in child.children], collection.name)

    # All other collections (all scenes)
    for collection in bpy.data.collections:
        if not shareData.collectionsInfo.get(collection.name):
            shareData.collectionsInfo[collection.name] = CollectionInfo(collection.hide_viewport, collection.instance_offset, [
                                                                        x.name for x in collection.children], None)
        for child in collection.children:
            shareData.collectionsInfo[child.name] = CollectionInfo(child.hide_viewport, child.instance_offset, [
                                                                   x.name for x in child.children], collection.name)

    # Store collections objects (already done for master collection above)
    for collection in bpy.data.collections:
        shareData.collectionsInfo[collection.name].objects = [x.name for x in collection.objects]


def updateObjectsState():
    objects = set([x.name for x in bpy.data.objects])
    shareData.objectsAdded = objects - shareData.objects
    shareData.objectsRemoved = shareData.objects - objects

    if len(shareData.objectsAdded) == 1 and len(shareData.objectsRemoved) == 1:
        shareData.objectsRenamed[list(shareData.objectsRemoved)[0]] = list(shareData.objectsAdded)[0]
        shareData.objectsAdded.clear()
        shareData.objectsRemoved.clear()
        return

    for objName, visible in shareData.objectsVisibility.items():
        newObj = bpy.data.objects.get(objName)
        if newObj and visible != newObj.hide_viewport:
            shareData.objectsVisibilityChanged.add(objName)

    for objName, parent in shareData.objectsParents.items():
        newObj = bpy.data.objects.get(objName)
        if not newObj:
            continue
        newObjParent = "" if newObj.parent == None else newObj.parent.name
        if newObjParent != parent:
            shareData.objectsReparented.add(objName)

    for objName, transform in shareData.objectsTransforms.items():
        newObj = bpy.data.objects.get(objName)
        if not newObj:
            continue
        matrix = newObj.matrix_local
        t = matrix.to_translation()
        r = matrix.to_quaternion()
        s = matrix.to_scale()
        if t != transform[0] or r != transform[1] or s != transform[2]:
            shareData.objectsTransformed.add(objName)


def updateObjectsInfo():
    shareData.objects = set([x.name for x in bpy.data.objects])
    shareData.objectsVisibility = dict((x.name, x.hide_viewport) for x in bpy.data.objects)
    shareData.objectsParents = dict((x.name, x.parent.name if x.parent != None else "") for x in bpy.data.objects)

    shareData.objectsTransforms = {}
    for obj in bpy.data.objects:
        matrix = obj.matrix_local
        t = matrix.to_translation()
        r = matrix.to_quaternion()
        s = matrix.to_scale()
        shareData.objectsTransforms[obj.name] = (t, r, s)


def updateCurrentData():
    updateCollectionsInfo()
    updateObjectsInfo()


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
    for collection in bpy.data.collections:
        info = shareData.collectionsInfo.get(collection.name)
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
        if objName in bpy.data.objects:
            updateTransform(bpy.data.objects[objName])
            changed = True
    return changed


def updateObjectsTransforms():
    changed = False
    for objName in shareData.objectsTransformed:
        if objName in bpy.data.objects:
            updateTransform(bpy.data.objects[objName])
            changed = True
    return changed


def reparentObjects():
    changed = False
    for objName in shareData.objectsReparented:
        if objName in bpy.data.objects:
            updateTransform(bpy.data.objects[objName])
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
def sendSceneDataToServer(scene):
    shareData.clearLists()

    # prevent processing self events
    if shareData.client.receivedCommandsProcessed:
        if not shareData.client.blockSignals:
            shareData.client.receivedCommandsProcessed = False
        return

    if shareData.client.currentSceneName != bpy.context.scene.name:
        updateCurrentData()
        updateSceneChanged()
        return

    if not isInObjectMode():
        return

    updateObjectsState()
    updateCollectionsState()

    changed = False
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
        shareData.depsgraph = bpy.context.evaluated_depsgraph_get()
        updateObjectsData()

    # update for next change
    updateCurrentData()


@persistent
def onUndoRedoPre(scene):
    #shareData.selectedObjectsNames = set()
    # for obj in bpy.context.selected_objects:
    #    shareData.selectedObjectsNames.add(obj.name)
    if not isInObjectMode():
        return

    shareData.client.currentSceneName = bpy.context.scene.name

    shareData.clearLists()
    updateCurrentData()


@persistent
def onUndoRedoPost(scene):
    # apply only in object mode
    if not isInObjectMode():
        return

    if shareData.client.currentSceneName != bpy.context.scene.name:
        updateSceneChanged()
        return

    updateObjectsState()
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
        shareData.client.sendAddObjectToCollection(collection.name, obj.name)

    for childCollection in collection.children:
        shareData.client.sendAddCollectionToCollection(collection.name, childCollection.name)


def send_collections():
    for collection in bpy.data.collections:
        shareData.client.sendCollection(collection)
        send_collection_content(collection)


def send_scene_content():
    logger.info("Sending scene content to server")

    shareData.client.currentSceneName = bpy.context.scene.name

    # First step : Send all Blender data (materials, objects, collection) existing in file
    # ====================================================================================

    # send materials
    for material in bpy.data.materials:
        shareData.client.sendMaterial(material)

    # send objects
    for obj in bpy.data.objects:
        updateParams(obj)
        updateTransform(obj)

    # send all collections
    send_collections()

    # Second step : send current scene content
    # ========================================
    shareData.client.sendSetCurrentScene(bpy.context.scene.name)

    # send scene objects
    for obj in bpy.context.scene.objects:
        shareData.client.sendSceneObject(obj)

    # send scene collections
    for col in bpy.context.scene.collection.children:
        shareData.client.sendSceneCollection(col)


def set_handlers(connect: bool):
    try:
        if connect:
            shareData.depsgraph = bpy.context.evaluated_depsgraph_get()
            bpy.app.handlers.frame_change_post.append(sendSceneDataToServer)
            bpy.app.handlers.depsgraph_update_post.append(sendSceneDataToServer)
            bpy.app.handlers.undo_pre.append(onUndoRedoPre)
            bpy.app.handlers.redo_pre.append(onUndoRedoPre)
            bpy.app.handlers.undo_post.append(onUndoRedoPost)
            bpy.app.handlers.redo_post.append(onUndoRedoPost)
            bpy.app.handlers.load_post.append(onLoad)
        else:
            bpy.app.handlers.load_post.remove(onLoad)
            bpy.app.handlers.frame_change_post.remove(sendSceneDataToServer)
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
        args = {'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT}

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
            bpy.ops.dcc_sync.joinroom()
            room = shareData.currentRoom

        hostname = "localhost"
        if not shareData.isLocal:
            hostname = vrtistconnect.host
        args = [dcc_sync_props.VRtist, "--room", room, "--hostname", hostname, "--port", str(vrtistconnect.port)]
        subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        return {'FINISHED'}


classes = (
    LaunchVRtistOperator,
    CreateRoomOperator,
    UpdateRoomListOperator,
    SendSelectionOperator,
    JoinOrLeaveRoomOperator,
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
