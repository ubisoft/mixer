import os
import logging
import tempfile
import random
from datetime import datetime
from pathlib import Path

import bpy

from mixer.broadcaster import common
from mixer.broadcaster.common import ClientMetadata, RoomMetadata
from mixer.share_data import share_data
from mixer.stats import get_stats_directory

logger = logging.getLogger(__name__)


class RoomItem(bpy.types.PropertyGroup):
    def is_room_experimental(self):
        if self.name in share_data.rooms_dict and "experimental_sync" in share_data.rooms_dict[self.name]:
            return share_data.rooms_dict[self.name]["experimental_sync"]
        return False

    def is_kept_open(self):
        if self.name in share_data.rooms_dict and RoomMetadata.KEEP_OPEN in share_data.rooms_dict[self.name]:
            return share_data.rooms_dict[self.name][RoomMetadata.KEEP_OPEN]
        return False

    def on_keep_open_changed(self, value):
        share_data.client.set_room_keep_open(self.name, value)
        return None

    name: bpy.props.StringProperty(name="Name")
    users_count: bpy.props.IntProperty(name="Users Count")
    experimental_sync: bpy.props.BoolProperty(name="Experimental Sync", get=is_room_experimental)
    keep_open: bpy.props.BoolProperty(name="Keep Open", default=False, get=is_kept_open, set=on_keep_open_changed)


class UserWindowItem(bpy.types.PropertyGroup):
    scene: bpy.props.StringProperty(name="Scene")
    view_layer: bpy.props.StringProperty(name="View Layer")
    screen: bpy.props.StringProperty(name="Screen")
    areas_3d_count: bpy.props.IntProperty(name="3D Areas Count")


class UserSceneItem(bpy.types.PropertyGroup):
    scene: bpy.props.StringProperty(name="Scene")
    frame: bpy.props.IntProperty(name="Frame")


class UserItem(bpy.types.PropertyGroup):
    is_me: bpy.props.BoolProperty(name="Is Me")
    name: bpy.props.StringProperty(name="Name")
    ip: bpy.props.StringProperty(name="IP")
    port: bpy.props.IntProperty(name="Port")
    ip_port: bpy.props.StringProperty(name="IP:Port")
    room: bpy.props.StringProperty(name="Room")
    internal_color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR")
    color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR", get=lambda self: self.internal_color)
    windows: bpy.props.CollectionProperty(name="Windows", type=UserWindowItem)
    selected_window_index: bpy.props.IntProperty(name="Window Index")
    scenes: bpy.props.CollectionProperty(name="Scenes", type=UserSceneItem)


def stats_file_path_suffix():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def get_logs_directory():
    def _get_logs_directory():
        if "MIXER_USER_LOGS_DIR" in os.environ:
            username = os.getlogin()
            base_shared_path = Path(os.environ["MIXER_USER_LOGS_DIR"])
            if os.path.exists(base_shared_path):
                return os.path.join(os.fspath(base_shared_path), username)
            logger.error(
                f"MIXER_USER_LOGS_DIR env var set to {base_shared_path}, but directory does not exists. Falling back to default location."
            )
        return os.path.join(os.fspath(tempfile.gettempdir()), "mixer")

    dir = _get_logs_directory()
    if not os.path.exists(dir):
        os.makedirs(dir)
    return dir


def get_log_file():
    return os.path.join(get_logs_directory(), f"mixer_logs_{share_data.runId}.log")


def gen_random_color():
    r = random.random()
    g = random.random()
    b = random.random()
    return [r, g, b]


def set_log_level(self, value):
    logging.getLogger(__package__).setLevel(value)
    logger.log(value, "Logging level changed")


class MixerPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def on_user_changed(self, context):
        client = share_data.client
        if client and client.is_connected():
            client.set_client_metadata({ClientMetadata.USERNAME: self.user})

    def on_user_color_changed(self, context):
        client = share_data.client
        if client and client.is_connected():
            client.set_client_metadata({ClientMetadata.USERCOLOR: list(self.color)})

    # Allows to change behavior according to environment: production or development
    env: bpy.props.EnumProperty(
        name="Execution Environment",
        description="Execution environment: production, development or testing",
        items=[
            ("production", "production", "", 0),
            ("development", "development", "", 1),
            ("testing", "testing", "", 2),
        ],
        default=os.environ.get("MIXER_ENV", "production"),
    )

    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=int(os.environ.get("VRTIST_PORT", common.DEFAULT_PORT)))
    room: bpy.props.StringProperty(name="Room", default=os.environ.get("VRTIST_ROOM", os.getlogin()))

    # User name as displayed in peers user list
    user: bpy.props.StringProperty(name="User", default=os.getlogin(), update=on_user_changed)
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype="COLOR", default=gen_random_color(), update=on_user_color_changed
    )

    def get_log_level(self):
        return logging.getLogger(__package__).level

    log_level: bpy.props.EnumProperty(
        name="Log Level",
        description="Logging level to use",
        items=[
            ("ERROR", "Error", "", logging.ERROR),
            ("WARNING", "Warning", "", logging.WARNING),
            ("INFO", "Info", "", logging.INFO),
            ("DEBUG", "Debug", "", logging.DEBUG),
        ],
        set=set_log_level,
        get=get_log_level,
    )

    experimental_sync: bpy.props.BoolProperty(
        name="Experimental sync", default=os.environ.get("MIXER_EXPERIMENTAL_SYNC") is not None
    )

    show_server_console: bpy.props.BoolProperty(default=False)

    VRtist: bpy.props.StringProperty(
        name="VRtist", default=os.environ.get("VRTIST_EXE", "D:/unity/VRtist/Build/VRtist.exe"), subtype="FILE_PATH"
    )
    statistics_directory: bpy.props.StringProperty(
        name="Stats Directory", default=os.environ.get("MIXER_STATS_DIR", get_stats_directory()), subtype="FILE_PATH"
    )
    auto_save_statistics: bpy.props.BoolProperty(default=True)

    # Developer option to avoid sending scene content to server at the first connexion
    # Allow to quickly iterate debugging/test on large scenes with only one client in room
    # Main usage: optimization of client timers to check if updates are required
    no_send_scene_content: bpy.props.BoolProperty(default=False)

    send_base_meshes: bpy.props.BoolProperty(default=True)
    send_baked_meshes: bpy.props.BoolProperty(default=True)

    def draw(self, context):
        layout = self.layout
        layout.label(text="This is a preferences view for our add-on")


# This should probably be handled elsewhere, for now it is here
# We need a unique index for each user in snap_view_user and snap_time_user
# dropdown list otherwise the selection "pops" when a user leave room or
# disconnect
user_to_unique_index = {}
next_user_unique_index = 0


class MixerProperties(bpy.types.PropertyGroup):
    commands_send_interval: bpy.props.FloatProperty(
        name="Command Send Interval",
        description="Debug tool to specify a number of seconds to wait between each command emission toward the server.",
        default=0,
    )

    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty()  # index in the list of rooms

    # user list of the selected or connected room, according to status
    users: bpy.props.CollectionProperty(name="Users", type=UserItem)
    user_index: bpy.props.IntProperty()  # index in the list of users

    display_advanced_options: bpy.props.BoolProperty(default=False)
    display_developer_options: bpy.props.BoolProperty(default=False)
    display_rooms: bpy.props.BoolProperty(default=True)
    display_users: bpy.props.BoolProperty(default=True)

    display_users_filter: bpy.props.EnumProperty(
        name="Display Users Filter",
        description="Display users filter",
        items=[
            ("all", "All", "", 0),
            ("current_room", "Current Room", "", 1),
            ("selected_room", "Selected Room", "", 2),
            ("no_room", "No Room", "", 3),
        ],
        default="all",
    )
    display_users_details: bpy.props.BoolProperty(default=False, name="Display Users Details")

    display_snapping_options: bpy.props.BoolProperty(default=False)
    snap_view_user_enabled: bpy.props.BoolProperty(default=False)

    def update_user_to_unique_index_dict(self):
        global user_to_unique_index
        global next_user_unique_index
        for user in self.users:
            if user.ip_port not in user_to_unique_index:
                user_to_unique_index[user.ip_port] = next_user_unique_index
                next_user_unique_index += 1

    def get_snap_view_users(self, context):
        global user_to_unique_index

        self.update_user_to_unique_index_dict()

        # According to documentation:
        # There is a known bug with using a callback, Python must keep a reference
        # to the strings returned by the callback or Blender will misbehave or even crash.
        self.snap_view_users_values = [
            (user.ip_port, f"{user.name} ({user.ip_port})", "", user_to_unique_index[user.ip_port])
            for index, user in enumerate(self.users)
            if user.room == share_data.current_room  # and not user.is_me
        ]
        return self.snap_view_users_values

    def get_snap_view_area(self, context):
        # quick patch, see below todo for explanation
        self.snap_view_users_values = [("id", "", "")]
        return self.snap_view_users_values

        if self.snap_view_user == "":
            self.snap_view_areas_values = []
            return self.snap_view_areas_values

        scene = context.scene

        for user in self.users:
            if user.ip_port == self.snap_view_user:
                self.snap_view_areas_values = [
                    (f"window_{index}", f"Window {index} (Scene {window.scene})", "", index)
                    for index, window in enumerate(user.windows)
                    if window.scene == scene.name_full
                ]
                return self.snap_view_areas_values

        # According to documentation:
        # There is a known bug with using a callback, Python must keep a reference
        # to the strings returned by the callback or Blender will misbehave or even crash.
        self.snap_view_areas_values = []
        return self.snap_view_areas_values

    snap_view_user: bpy.props.EnumProperty(
        items=get_snap_view_users, name="Snap View User",
    )
    # todo: this cannot work, it depends on the 3d view panel
    # todo: so it should be a property of bpy.types.SpaceView3D probably.
    snap_view_area: bpy.props.EnumProperty(items=get_snap_view_area, name="Snap View 3D Area")

    snap_time_user_enabled: bpy.props.BoolProperty(default=False)
    snap_time_user: bpy.props.EnumProperty(
        items=get_snap_view_users, name="Snap Time User",
    )


def get_mixer_props() -> MixerProperties:
    return bpy.context.window_manager.mixer


def get_mixer_prefs() -> MixerPreferences:
    return bpy.context.preferences.addons[__package__].preferences


classes = (RoomItem, UserWindowItem, UserSceneItem, UserItem, MixerProperties, MixerPreferences)


def register():
    for _ in classes:
        bpy.utils.register_class(_)
    bpy.types.WindowManager.mixer = bpy.props.PointerProperty(type=MixerProperties)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
    del bpy.types.WindowManager.mixer
