import os
import bpy
from . import vrtistOperators


class VRtistPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "VRtist Panel"
    bl_idname = "OBJECT_PT_vrtist"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        row = layout.row()
        row.label(text="VRtist", icon='SCENE_DATA')

        row = layout.column()        
        row.operator("scene.vrtist", text="Launch VRTist")                        

        connected = vrtistOperators.shareData.client is not None and vrtistOperators.shareData.client.isConnected()
        if not connected:

            # Room list
            row = layout.row()
            row.template_list("ROOM_UL_ItemRenderer", "", scene.vrtistconnect, "rooms", scene.vrtistconnect, "room_index", rows=4)
            # Join room
            col = row.column()
            col.operator("scene.vrtistroomlistupdate", text="Refresh")
            col.operator("scene.vrtistjoinroom", text="Join Room")

            if scene.vrtistconnect.remoteServerIsUp:
                row =  layout.row()
                row.prop(scene.vrtistconnect, "room", text="Room")
                row.operator('scene.vrtistcreateroom', text='Create Room')

            col =  layout.column()
            row = col.row()
            row.prop(scene.vrtistconnect, "advanced",
                        icon="TRIA_DOWN" if scene.vrtistconnect.advanced else "TRIA_RIGHT",
                        icon_only=True, emboss=False)
            row.label(text = "Advanced options")
            if scene.vrtistconnect.advanced:
                col.prop(scene.vrtistconnect, "host", text="Host")
                col.prop(scene.vrtistconnect, "port", text="Port")
                col.prop(scene.vrtist, "VRtist", text="VRtist Path")

        else:            
            row.operator("scene.vrtistjoinroom", text="Leave Room")

