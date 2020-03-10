import bpy
import os
import logging
from datetime import datetime
from .broadcaster import common
from .shareData import shareData
from .stats import get_stats_directory
from . import ui


class RoomItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class UserItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class DCCSyncProperties(bpy.types.PropertyGroup):

    def on_room_selection_changed(self, context):
        ui.update_user_list()

    def on_user_changed(self, context):
        client = shareData.client
        if client and client.isConnected():
            client.setClientName(self.user)

    host: bpy.props.StringProperty(
        name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=common.DEFAULT_PORT)
    room: bpy.props.StringProperty(
        name="Room", default=os.environ.get("VRTIST_ROOM", os.getlogin()))
    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty(
        update=on_room_selection_changed)  # index in the list of rooms

    # User name as displayed in peers user list
    user: bpy.props.StringProperty(
        name="User", default=os.getlogin(), update=on_user_changed)

    # user list of the selected or connected room, according to status
    users: bpy.props.CollectionProperty(name="Users", type=UserItem)
    user_index: bpy.props.IntProperty()  # index in the list of users

    advanced: bpy.props.BoolProperty(default=False)
    developer_options: bpy.props.BoolProperty(default=False)
    remoteServerIsUp: bpy.props.BoolProperty(default=False)

    show_server_console_value = common.is_debugger_attached()
    logging.info("Debugger attached : %s ", show_server_console_value)
    showServerConsole: bpy.props.BoolProperty(
        default=show_server_console_value)

    VRtist: bpy.props.StringProperty(name="VRtist", default=os.environ.get(
        "VRTIST_EXE", "D:/unity/VRtist/Build/VRtist.exe"))
    statistics_directory: bpy.props.StringProperty(name="Stats Directory", default=os.environ.get(
        "DCCSYNC_STATS_DIR", get_stats_directory()))
    auto_save_statistics: bpy.props.BoolProperty(default=True)

    # Developer option to avoid sending scene content to server at the first connexion
    # Allow to quickly iterate debugging/test on large scenes with only one client in room
    # Main usage: optimization of client timers to check if updates are required
    no_send_scene_content: bpy.props.BoolProperty(default=False)


def get_dcc_sync_props() -> DCCSyncProperties:
    return bpy.context.window_manager.dcc_sync


classes = (
    RoomItem,
    UserItem,
    DCCSyncProperties,
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)
    bpy.types.WindowManager.dcc_sync = bpy.props.PointerProperty(
        type=DCCSyncProperties)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
    del bpy.types.WindowManager.dcc_sync
