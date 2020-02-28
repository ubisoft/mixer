import os
import bpy
from . import operators
from .data import get_dcc_sync_props


class ROOM_UL_ItemRenderer(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.row()
        split.label(text=item.name)  # avoids renaming the item by accident


class SettingsPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "DCC Sync"
    bl_idname = "DCCSYNC_PT_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "DCC Sync"

    def draw(self, context):
        layout = self.layout

        dcc_sync_props = get_dcc_sync_props()

        row = layout.row()
        row.label(text="VRtist", icon='SCENE_DATA')

        row = layout.column()
        row.operator(operators.LaunchVRtistOperator.bl_idname, text="Launch VRTist")

        row = layout.row()
        row.label(text="DCC Sync", icon='SCENE_DATA')

        row = layout.column()

        connected = operators.shareData.client is not None and operators.shareData.client.isConnected()
        if not connected:

            # Room list
            row = layout.row()
            row.template_list("ROOM_UL_ItemRenderer", "", dcc_sync_props,
                              "rooms", dcc_sync_props, "room_index", rows=4)
            # Join room
            col = row.column()
            col.operator(operators.UpdateRoomListOperator.bl_idname, text="Refresh")
            col.operator(operators.JoinOrLeaveRoomOperator.bl_idname, text="Join Room")

            if dcc_sync_props.remoteServerIsUp:
                row = layout.row()
                row.prop(dcc_sync_props, "room", text="Room")
                row.operator(operators.CreateRoomOperator.bl_idname, text='Create Room')

            col = layout.column()
            row = col.row()
            row.prop(dcc_sync_props, "advanced",
                     icon="TRIA_DOWN" if dcc_sync_props.advanced else "TRIA_RIGHT",
                     icon_only=True, emboss=False)
            row.label(text="Advanced options")
            if dcc_sync_props.advanced:
                col.prop(dcc_sync_props, "host", text="Host")
                col.prop(dcc_sync_props, "port", text="Port")
                col.prop(dcc_sync_props, "VRtist", text="VRtist Path")
                col.prop(dcc_sync_props, "showServerConsole", text="Show server console")

        else:
            row.operator(operators.JoinOrLeaveRoomOperator.bl_idname, text="Leave Room")

        col = layout.column()
        row = col.row()
        row.prop(dcc_sync_props, "developer_options",
                 icon="TRIA_DOWN" if dcc_sync_props.developer_options else "TRIA_RIGHT",
                 icon_only=True, emboss=False)
        row.label(text="Developer options")
        if dcc_sync_props.developer_options:
            col.prop(dcc_sync_props, "statistics_directory", text="Stats Directory")
            col.operator(operators.OpenStatsDirOperator.bl_idname, text="Open Directory")
            col.operator(operators.WriteStatisticsOperator.bl_idname, text="Write Statistics")
            col.prop(dcc_sync_props, "auto_save_statistics", text="Auto Save Statistics")
            col.prop(dcc_sync_props, "no_send_scene_content", text="No send_scene_content")


classes = (
    ROOM_UL_ItemRenderer,
    SettingsPanel
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
