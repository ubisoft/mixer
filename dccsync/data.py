import os
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import bpy

from dccsync.broadcaster import common
from dccsync.share_data import share_data
from dccsync.stats import get_stats_directory
from dccsync import ui

logger = logging.getLogger(__name__)


class RoomItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class UserItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


def stats_file_path_suffix():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


log_level_enum_items = [
    ("ERROR", "Error", "", logging.ERROR),
    ("WARNING", "Warning", "", logging.WARNING),
    ("INFO", "Info", "", logging.INFO),
    ("DEBUG", "Debug", "", logging.DEBUG),
]


def get_log_level(self):
    return logging.getLogger(__package__).level


def set_log_level(self, value):
    logging.getLogger(__package__).setLevel(value)
    logger.log(value, "Logging level changed")


def get_logs_directory():
    def _get_logs_directory():
        if "DCCSYNC_USER_LOGS_DIR" in os.environ:
            username = os.getlogin()
            base_shared_path = Path(os.environ["DCCSYNC_USER_LOGS_DIR"])
            if os.path.exists(base_shared_path):
                return os.path.join(os.fspath(base_shared_path), username)
            logger.error(
                f"DCCSYNC_USER_LOGS_DIR env var set to {base_shared_path}, but directory does not exists. Falling back to default location."
            )
        return os.path.join(os.fspath(tempfile.gettempdir()), "dcc_sync")

    dir = _get_logs_directory()
    if not os.path.exists(dir):
        os.makedirs(dir)
    return dir


def get_log_file():
    return os.path.join(get_logs_directory(), f"dccsync_logs_{share_data.runId}.log")


class DCCSyncProperties(bpy.types.PropertyGroup):
    def on_room_selection_changed(self, context):
        ui.update_user_list()

    def on_user_changed(self, context):
        client = share_data.client
        if client and client.is_connected():
            client.set_client_name(self.user)

    # Allows to change behavior according to environment: production or development
    env: bpy.props.StringProperty(name="Env", default=os.environ.get("DCCSYNC_ENV", "production"))

    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=common.DEFAULT_PORT)
    room: bpy.props.StringProperty(name="Room", default=os.environ.get("VRTIST_ROOM", os.getlogin()))
    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty(update=on_room_selection_changed)  # index in the list of rooms

    # User name as displayed in peers user list
    user: bpy.props.StringProperty(name="User", default=os.getlogin(), update=on_user_changed)

    # user list of the selected or connected room, according to status
    users: bpy.props.CollectionProperty(name="Users", type=UserItem)
    user_index: bpy.props.IntProperty()  # index in the list of users

    advanced: bpy.props.BoolProperty(default=False)
    developer_options: bpy.props.BoolProperty(default=False)
    remote_server_is_up: bpy.props.BoolProperty(default=False)

    show_server_console: bpy.props.BoolProperty(default=False)

    VRtist: bpy.props.StringProperty(
        name="VRtist", default=os.environ.get("VRTIST_EXE", "D:/unity/VRtist/Build/VRtist.exe")
    )
    statistics_directory: bpy.props.StringProperty(
        name="Stats Directory", default=os.environ.get("DCCSYNC_STATS_DIR", get_stats_directory())
    )
    auto_save_statistics: bpy.props.BoolProperty(default=True)

    # Developer option to avoid sending scene content to server at the first connexion
    # Allow to quickly iterate debugging/test on large scenes with only one client in room
    # Main usage: optimization of client timers to check if updates are required
    no_send_scene_content: bpy.props.BoolProperty(default=False)

    send_base_meshes: bpy.props.BoolProperty(default=True)
    send_baked_meshes: bpy.props.BoolProperty(default=True)

    log_level: bpy.props.EnumProperty(
        name="Log Level",
        description="Logging level to use",
        items=log_level_enum_items,
        set=set_log_level,
        get=get_log_level,
    )

    experimental_sync: bpy.props.BoolProperty(
        name="Experimental sync", default=os.environ.get("DCCSYNC_EXPERIMENTAL_SYNC") is not None
    )


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
    bpy.types.WindowManager.dcc_sync = bpy.props.PointerProperty(type=DCCSyncProperties)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
    del bpy.types.WindowManager.dcc_sync
