import os
import bpy
from . import operators


class ROOM_UL_ItemRenderer(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.row()
        split.label(text=item.name)  # avoids renaming the item by accident


class VRtistPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "VRtist"
    bl_idname = "VRTIST_PT_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "VRtist"

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        row = layout.row()
        row.label(text="VRtist", icon='SCENE_DATA')

        row = layout.column()
        row.operator("scene.vrtist", text="Launch VRTist")
        row.operator(operators.VRtistSayHello.bl_idname, text="Say Hello")

        connected = operators.shareData.client is not None and operators.shareData.client.isConnected()
        if not connected:

            # Room list
            row = layout.row()
            row.template_list("ROOM_UL_ItemRenderer", "", scene.vrtistconnect,
                              "rooms", scene.vrtistconnect, "room_index", rows=4)
            # Join room
            col = row.column()
            col.operator("scene.vrtistroomlistupdate", text="Refresh")
            col.operator("scene.vrtistjoinroom", text="Join Room")

            if scene.vrtistconnect.remoteServerIsUp:
                row = layout.row()
                row.prop(scene.vrtistconnect, "room", text="Room")
                row.operator('scene.vrtistcreateroom', text='Create Room')

            col = layout.column()
            row = col.row()
            row.prop(scene.vrtistconnect, "advanced",
                     icon="TRIA_DOWN" if scene.vrtistconnect.advanced else "TRIA_RIGHT",
                     icon_only=True, emboss=False)
            row.label(text="Advanced options")
            if scene.vrtistconnect.advanced:
                col.prop(scene.vrtistconnect, "host", text="Host")
                col.prop(scene.vrtistconnect, "port", text="Port")
                col.prop(scene.vrtistconnect, "VRtist", text="VRtist Path")

        else:
            row.operator("scene.vrtistjoinroom", text="Leave Room")


classes = (
    ROOM_UL_ItemRenderer,
    VRtistPanel
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
