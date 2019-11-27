import bpy
from .broadcaster.client import Client
from . import geometry
from .broadcaster import common

class VRtistConnectProperties(bpy.types.PropertyGroup):
    host: bpy.props.StringProperty(name="Host", default="localhost")
    port: bpy.props.IntProperty(name="Port", default=12800)

class VRtistConnectOperator(bpy.types.Operator):
    bl_idname = "scene.vrtistconnect"
    bl_label = "VRtist Server"
    bl_options = {'REGISTER', 'UNDO'}
    
    #vrtist = bpy.data.scenes[0].vrtist.VRtist
    
    def execute(self, context):        
        host = bpy.data.scenes[0].vrtistconnect.host
        port = bpy.data.scenes[0].vrtistconnect.port
        self.client = Client(host, port)
        #self.client.joinRoom(bpy.data.filepath)
        self.client.joinRoom("toto")

        selectedObjects = bpy.context.selected_objects
        if len(selectedObjects) > 0:
            buffer = geometry.getMeshBuffers(selectedObjects[0].data)
            self.client.addCommand(common.Command(common.MessageType.MESH, buffer))

        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(VRtistConnectOperator.bl_idname)
