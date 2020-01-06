import os
import sys
import subprocess
import shutil
from pathlib import Path

import bpy
import socket
from mathutils import *
from . import clientBlender
from .broadcaster import common
from bpy.app.handlers import persistent
from bpy.types import UIList

HOST = 'localhost'
PORT = 12800


class ShareData:
    def __init__(self):
        self.client = None
        self.currentRoom = None
        self.isLocal = False
        self.localServerProcess = None
        self.selectedObjectsNames = []
        self.depsgraph = None
        self.roomListUpdateClient = None

shareData = ShareData()


class VRtistRoomItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class VRtistConnectProperties(bpy.types.PropertyGroup):
    #host: bpy.props.StringProperty(name="Host", default="lgy-wks-052279")
    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST","localhost"))
    port: bpy.props.IntProperty(name="Port", default=PORT)
    room: bpy.props.StringProperty(name="Room", default=os.getlogin())
    rooms: bpy.props.CollectionProperty(name="Rooms", type=VRtistRoomItem)
    room_index: bpy.props.IntProperty()  # index in the list of rooms
    advanced: bpy.props.BoolProperty(default=False)
    remoteServerIsUp: bpy.props.BoolProperty(default=False)
    VRtist: bpy.props.StringProperty(name="VRtist", default=os.environ.get("VRTIST_EXE","D:/unity/VRtist/Build/VRtist.exe"))

def updateParams(obj):
    if not hasattr(obj, "data"):
        return
    
    typename = obj.bl_rna.name
    if obj.data:
        typename = obj.data.bl_rna.name
    
    if  typename != 'Camera' and typename != 'Mesh' and typename != 'Sun Light' and typename != 'Point Light' and typename != 'Spot Light':
        return

    if typename == 'Camera':
        shareData.client.sendCamera(obj)

    if typename == 'Sun Light' or typename == 'Point Light' or typename == 'Spot Light':
        shareData.client.sendLight(obj)

    if typename == 'Mesh':
        shareData.client.sendMesh(obj)
        shareData.client.sendMeshConnection(obj)


def updateTransform(obj):
    if not hasattr(obj, "data"):
        return

    typename = obj.bl_rna.name   
    if obj.data:
        typename = obj.data.bl_rna.name

    if typename != 'Object' and typename != 'Camera' and typename != 'Mesh' and typename != 'Sun Light' and typename != 'Point Light' and typename != 'Spot Light':
        return
    shareData.client.sendTransform(obj)

@persistent
def onLoad(scene):
    connected = shareData.client is not None and shareData.client.isConnected()
    if connected:
        set_handlers(False)

        if bpy.app.timers.is_registered(shareData.client.networkConsumer):
            bpy.app.timers.unregister(shareData.client.networkConsumer)

        if shareData.client is not None:
            shareData.client.disconnect()
            del(shareData.client)
            shareData.client = None

@persistent
def onUndoRedoPre(scene):
    shareData.selectedObjectsNames = set()
    for obj in bpy.context.selected_objects:        
        shareData.selectedObjectsNames.add(obj.name)


@persistent
def onUndoRedoPost(scene):
    # apply only in object mode
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        return

    nameSet = set()
    for obj in bpy.context.selected_objects:
        nameSet.add(obj.name)

    for name in shareData.selectedObjectsNames:
        if name not in nameSet and name not in bpy.data.objects:
            shareData.client.sendDelete(shareData.client.syncObjects[name])
            del shareData.client.objectNames[name]
            del shareData.client.syncObjects[name]

    for name in shareData.client.objectNames:
        if name in bpy.data.objects:
            shareData.client.objectNames[name] = bpy.data.objects[name]
        
    materials = set({})
    for obj in bpy.context.selected_objects:
        if hasattr(obj, "material_slots"):
            for slot in obj.material_slots[:]:    
                materials.add(slot.material)

    for material in materials:                
        shareData.client.sendMaterial(material)

    for obj in bpy.context.selected_objects:
        updateParams(obj)
        updateTransform(obj)

    shareData.client.internalUpdate()
    shareData.depsgraph = bpy.context.evaluated_depsgraph_get()


@persistent
def sendSceneDataToServer(scene):
    shareData.depsgraph = bpy.context.evaluated_depsgraph_get()

    # flush pending commands to update transform cache
    # shareData.client.networkConsumer()
    if shareData.client.receivedCommandsProcessed:
        shareData.client.receivedCommandsProcessed = False
        return
    
    if not hasattr(bpy.context,"active_object") or (bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT'):
        return

    shareData.client.sendDeletedRenamedReparentedObjects()

    # parse modifications
    container = {}
    materials = set({})
    transforms = set()
    data = set()    
    for update in shareData.depsgraph.updates:
        obj = update.id.original        
        
        typename = obj.bl_rna.name
        if typename == 'Object':
            if hasattr(obj, 'data'):
                container[obj.data] = obj
            transforms.add(obj)
        if typename == 'Material':
            materials.add(obj)
        if typename == typename == 'Camera' or typename == 'Mesh' or typename == 'Sun Light' or typename == 'Point Light' or typename == 'Spot Light':
            data.add(obj)

    for material in materials:
        shareData.client.sendMaterial(material)
    
    for d in data:
        if d in container:
            updateParams(container[d])

    for t in transforms:
        updateTransform(t)


rooms_cache = None
getting_rooms = False

def updateListRoomsProperty():
    bpy.data.scenes[0].vrtistconnect.rooms.clear()
    if rooms_cache:
        for room in rooms_cache:
            item = bpy.data.scenes[0].vrtistconnect.rooms.add()
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
    bpy.data.scenes[0].vrtistconnect.rooms.clear()
    localItem = bpy.data.scenes[0].vrtistconnect.rooms.add()
    localItem.name = "Local"
    VRtistRoomListUpdateOperator.rooms_cached = True

def getRooms(force=False):
    global getting_rooms, rooms_cache
    if getting_rooms:
        return

    if not force and rooms_cache:
        return

    host = bpy.data.scenes[0].vrtistconnect.host
    port = bpy.data.scenes[0].vrtistconnect.port  
    shareData.roomListUpdateClient = None
    
    up = server_is_up(host, port)
    bpy.data.scenes[0].vrtistconnect.remoteServerIsUp = up

    if up:
        shareData.roomListUpdateClient = clientBlender.ClientBlender(host, port)

    if not up or not shareData.roomListUpdateClient.isConnected():
        rooms_cache = ["Local"]
        return

    getting_rooms = True
    if not bpy.app.timers.is_registered(shareData.roomListUpdateClient.networkConsumer):
        bpy.app.timers.register(shareData.roomListUpdateClient.networkConsumer)

    shareData.roomListUpdateClient.addCallback('roomsList', onRooms)
    shareData.roomListUpdateClient.sendListRooms()

class VRtistRoomListUpdateOperator(bpy.types.Operator):
    bl_idname = "scene.vrtistroomlistupdate"
    bl_label = "VRtist Update Room List"
    bl_options = {'REGISTER'}

    def execute(self, context):
        getRooms(force=True)
        updateListRoomsProperty()
        return {'FINISHED'} 

class ROOM_UL_ItemRenderer(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.row()
        split.label(text=item.name) # avoids renaming the item by accident

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

def send_scene_content():
    for material in bpy.data.materials:
        shareData.client.sendMaterial(material)

    for obj in bpy.context.scene.objects:
        updateParams(obj)
        updateTransform(obj)


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
        print ("Error setting handlers")


class VRtistCreateRoomOperator(bpy.types.Operator):
    bl_idname = "scene.vrtistcreateroom"
    bl_label = "VRtist Create Room"
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
            room = bpy.data.scenes[0].vrtistconnect.room
            host = bpy.data.scenes[0].vrtistconnect.host
            port = bpy.data.scenes[0].vrtistconnect.port

            shareData.client = clientBlender.ClientBlender(host, port)
            shareData.client.addCallback('SendContent',send_scene_content)
            shareData.client.addCallback('ClearContent',clear_scene_content)
            if not shareData.client.isConnected():
                    return {'CANCELLED'}

            if not bpy.app.timers.is_registered(shareData.client.networkConsumer):
                bpy.app.timers.register(shareData.client.networkConsumer)

            shareData.client.joinRoom(room)
            shareData.currentRoom = room

            set_handlers(True)
            VRtistRoomListUpdateOperator.rooms_cached = False
        return {'FINISHED'}

def start_local_server():
    dir_path = Path(__file__).parent
    pythonPath = Path(sys.argv[0]).parent / (str(bpy.app.version[0]) + "." + str(bpy.app.version[1])) / 'python' / 'bin' / 'python'
    serverPath = dir_path / 'broadcaster' / 'dccBroadcaster.py'
    shareData.localServerProcess = subprocess.Popen([str(pythonPath), str(serverPath)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT, shell=False)

def server_is_up(address, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((address, port))
        s.shutdown(socket.SHUT_RDWR)
        s.close()
        return True
    except:
        return False    

class VRtistJoinRoomOperator(bpy.types.Operator):
    bl_idname = "scene.vrtistjoinroom"
    bl_label = "VRtist Join Room"
    bl_options = {'REGISTER'}   

    def execute(self, context):
        global rooms_cache

        shareData.currentRoom = None
        connected = shareData.client is not None and shareData.client.isConnected()
        if connected:
            set_handlers(False)

            if bpy.app.timers.is_registered(shareData.client.networkConsumer):
                bpy.app.timers.unregister(shareData.client.networkConsumer)

            if shareData.client is not None:
                shareData.client.disconnect()
                del(shareData.client)
                shareData.client = None
            VRtistRoomListUpdateOperator.rooms_cached = False
        else:
            shareData.isLocal = False
            try:
                roomIndex = bpy.data.scenes[0].vrtistconnect.room_index
                room = bpy.data.scenes[0].vrtistconnect.rooms[roomIndex].name
            except IndexError:
                room = "Local"

            localServerIsUp = True
            if room == 'Local':
                host = HOST
                port = PORT
                localServerIsUp = server_is_up(host, port)                
                # Launch local server? if it doesn't exist
                if not localServerIsUp:
                    start_local_server()
                shareData.isLocal = True
            else:
                host = bpy.data.scenes[0].vrtistconnect.host
                port = bpy.data.scenes[0].vrtistconnect.port

            shareData.client = clientBlender.ClientBlender(host, port)
            shareData.client.addCallback('SendContent',send_scene_content)
            shareData.client.addCallback('ClearContent',clear_scene_content)
            if not shareData.client.isConnected():
                    return {'CANCELLED'}
            if not bpy.app.timers.is_registered(shareData.client.networkConsumer):
                bpy.app.timers.register(shareData.client.networkConsumer)

            shareData.client.joinRoom(room)
            set_handlers(True)

            shareData.currentRoom = room

        return {'FINISHED'}


class VRtistSendSelectionOperator(bpy.types.Operator):
    bl_idname = "scene.vrtistsendselection"
    bl_label = "VRtist Send Selection"
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
                print( 'materials not found' )


            updateParams(obj)
            updateTransform(obj)

        return {'FINISHED'}


class VRtistOperator(bpy.types.Operator):
    bl_idname = "scene.vrtist"
    bl_label = "VRtist"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        vrtistconnect =  bpy.data.scenes[0].vrtistconnect
        room = shareData.currentRoom
        if not room:
            bpy.ops.scene.vrtistjoinroom()
            room = shareData.currentRoom

        hostname = "localhost"
        if not shareData.isLocal:
            hostname = vrtistconnect.host
        args = [bpy.data.scenes[0].vrtistconnect.VRtist, "--room",room, "--hostname", hostname, "--port", str(vrtistconnect.port)]
        subprocess.Popen(args, stdout=subprocess.PIPE,stderr=subprocess.STDOUT, shell=False)
        return {'FINISHED'}    
