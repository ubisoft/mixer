import bpy
from . import operators
from .data import get_dcc_sync_props, DCCSyncProperties
from .shareData import shareData

import logging

logger = logging.Logger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger.setLevel(logging.INFO)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'UI':
                        region.tag_redraw()
                        break


def redraw_if(condition: bool):
    if condition:
        redraw()


def update_ui_lists():
    update_room_list(do_redraw=False)
    update_user_list()


def update_user_list(do_redraw=True):
    props = get_dcc_sync_props()
    props.users.clear()
    if shareData.client_ids is None:
        redraw_if(do_redraw)
        return

    if shareData.currentRoom:
        room_name = shareData.currentRoom
    else:
        idx = props.room_index
        if idx >= len(props.rooms):
            redraw_if(do_redraw)
            return
        room_name = props.rooms[idx].name

    client_ids = [c for c in shareData.client_ids if c['room'] == room_name]

    for client in client_ids:
        item = props.users.add()
        display_name = client['name']
        display_name = display_name if display_name is not None else "<unnamed>"
        display_name = f"{display_name} ({client['ip']}:{client['port']})"
        item.name = display_name

    redraw_if(do_redraw)


def update_room_list(do_redraw=True):
    props = get_dcc_sync_props()
    props.rooms.clear()
    if shareData.client_ids is None:
        redraw_if(do_redraw)
        return

    rooms = {id['room'] for id in shareData.client_ids if id['room']}
    for room in rooms:
        item = props.rooms.add()
        item.name = room

    redraw_if(do_redraw)


class ROOM_UL_ItemRenderer(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.row()
        split.label(text=item.name)  # avoids renaming the item by accident


class USERS_UL_ItemRenderer(bpy.types.UIList):
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
        logger.debug("SettingsPanel::draw()")
        layout = self.layout

        dcc_sync_props = get_dcc_sync_props()

        row = layout.row()
        row.label(text="VRtist", icon='SCENE_DATA')

        row = layout.column()
        row.operator(operators.LaunchVRtistOperator.bl_idname, text="Launch VRTist")

        row = layout.row()
        row.label(text="DCC Sync", icon='SCENE_DATA')

        row = layout.column()

        if not operators.shareData.currentRoom:

            # Room list
            row = layout.row()
            row.template_list("ROOM_UL_ItemRenderer", "", dcc_sync_props,
                              "rooms", dcc_sync_props, "room_index", rows=4)

            # Join room
            col = row.column()

            connected = operators.shareData.client is not None and operators.shareData.client.isConnected()
            if not connected:
                col.operator(operators.ConnectOperator.bl_idname, text="Connect")
            else:
                col.operator(operators.DisconnectOperator.bl_idname, text="Disconnect")
            col.operator(operators.JoinRoomOperator.bl_idname, text="Join Room")

            row = layout.row()
            col = row.column()
            col.label(text="Room Users: ")
            col.template_list("USERS_UL_ItemRenderer", "", dcc_sync_props,
                              "users", dcc_sync_props, "user_index", rows=4)

            row = layout.row()
            row.prop(dcc_sync_props, "room", text="Room")
            row.operator(operators.CreateRoomOperator.bl_idname, text='Create Room')
            row = layout.row()
            row.prop(dcc_sync_props, "user", text="User")

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
            col = row.column()
            col.operator(operators.LeaveRoomOperator.bl_idname,
                         text=f"Leave Room : {operators.shareData.currentRoom}")
            col.label(text="Room Users: ")
            col.template_list("USERS_UL_ItemRenderer", "", dcc_sync_props,
                              "users", dcc_sync_props, "user_index", rows=4)

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
            col.prop(dcc_sync_props, "send_base_meshes", text="Send Base Meshes")
            col.prop(dcc_sync_props, "send_baked_meshes", text="Send Baked Meshes")


classes = (
    ROOM_UL_ItemRenderer,
    USERS_UL_ItemRenderer,
    SettingsPanel
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
