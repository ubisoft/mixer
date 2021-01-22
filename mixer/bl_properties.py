# GPLv3 License
#
# Copyright (C) 2020 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This module defines Blender Property types for the addon.
"""

import logging

import bpy

from mixer.broadcaster.common import RoomAttributes
from mixer.os_utils import getuser
from mixer.share_data import share_data

logger = logging.getLogger(__name__)


class RoomItem(bpy.types.PropertyGroup):
    def get_room_blender_version(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and "blender_version" in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name]["blender_version"]
        return ""

    def get_room_mixer_version(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and "mixer_version" in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name]["mixer_version"]
        return ""

    def is_ignore_version_check(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and "ignore_version_check" in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name]["ignore_version_check"]
        return False

    def get_protocol(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and "generic_protocol" in share_data.client.rooms_attributes[self.name]
        ):
            return "Generic" if share_data.client.rooms_attributes[self.name]["generic_protocol"] else "VRtist"
        return ""

    def is_kept_open(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and RoomAttributes.KEEP_OPEN in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name][RoomAttributes.KEEP_OPEN]
        return False

    def on_keep_open_changed(self, value):
        share_data.client.set_room_keep_open(self.name, value)
        return None

    def get_command_count(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and RoomAttributes.COMMAND_COUNT in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name][RoomAttributes.COMMAND_COUNT]
        return 0

    def get_mega_byte_size(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and RoomAttributes.BYTE_SIZE in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name][RoomAttributes.BYTE_SIZE] * 1e-6
        return 0

    def is_joinable(self):
        if (
            share_data.client is not None
            and self.name in share_data.client.rooms_attributes
            and RoomAttributes.JOINABLE in share_data.client.rooms_attributes[self.name]
        ):
            return share_data.client.rooms_attributes[self.name][RoomAttributes.JOINABLE]
        return False

    name: bpy.props.StringProperty(name="Name")
    blender_version: bpy.props.StringProperty(name="Blender Version", get=get_room_blender_version)
    mixer_version: bpy.props.StringProperty(name="Mixer Version", get=get_room_mixer_version)
    ignore_version_check: bpy.props.BoolProperty(name="Ignore Version Check", get=is_ignore_version_check)
    users_count: bpy.props.IntProperty(name="Users Count")
    protocol: bpy.props.StringProperty(name="Protocol", get=get_protocol)
    keep_open: bpy.props.BoolProperty(name="Keep Open", default=False, get=is_kept_open, set=on_keep_open_changed)
    command_count: bpy.props.IntProperty(name="Command Count", get=get_command_count)
    mega_byte_size: bpy.props.FloatProperty(name="Mega Byte Size", get=get_mega_byte_size)
    joinable: bpy.props.BoolProperty(name="Joinable", get=is_joinable)


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


# This should probably be handled elsewhere, for now it is here
# We need a unique index for each user in snap_view_user and snap_time_user
# dropdown list otherwise the selection "pops" when a user leave room or
# disconnect
user_to_unique_index = {}
next_user_unique_index = 0


class SharedFolderItem(bpy.types.PropertyGroup):
    shared_folder: bpy.props.StringProperty(default="", subtype="DIR_PATH", name="Shared Folder")


class MixerProperties(bpy.types.PropertyGroup):
    """
    Main Property class, registered on the WindowManager.
    Store non-persistent options and data to be displayed on the UI.
    """

    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty()  # index in the list of rooms

    # user list of the selected or connected room, according to status
    users: bpy.props.CollectionProperty(name="Users", type=UserItem)
    user_index: bpy.props.IntProperty()  # index in the list of users

    display_shared_folders_options: bpy.props.BoolProperty(default=True)
    display_advanced_options: bpy.props.BoolProperty(default=False)
    display_developer_options: bpy.props.BoolProperty(default=False)
    display_rooms: bpy.props.BoolProperty(default=True)
    display_rooms_details: bpy.props.BoolProperty(default=False, name="Display Rooms Details")
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

    shared_folders: bpy.props.CollectionProperty(name="Shared Folders", type=SharedFolderItem)
    shared_folder_index: bpy.props.IntProperty()

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
            if user.room == share_data.client.current_room
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
        items=get_snap_view_users,
        name="Snap View User",
    )
    # todo: this cannot work, it depends on the 3d view panel
    # todo: so it should be a property of bpy.types.SpaceView3D probably.
    snap_view_area: bpy.props.EnumProperty(items=get_snap_view_area, name="Snap View 3D Area")

    snap_time_user_enabled: bpy.props.BoolProperty(default=False)
    snap_time_user: bpy.props.EnumProperty(
        items=get_snap_view_users,
        name="Snap Time User",
    )

    snap_3d_cursor_user_enabled: bpy.props.BoolProperty(default=False)
    snap_3d_cursor_user: bpy.props.EnumProperty(
        items=get_snap_view_users,
        name="Snap 3D Cursor User",
    )

    display_advanced_room_control: bpy.props.BoolProperty(default=False)
    upload_room_name: bpy.props.StringProperty(default=f"{getuser()}_uploaded_room", name="Upload Room Name")
    upload_room_filepath: bpy.props.StringProperty(default="", subtype="FILE_PATH", name="Upload Room File")

    joining_percentage: bpy.props.FloatProperty(default=0, name="Joining Percentage")


classes = (
    RoomItem,
    UserWindowItem,
    UserSceneItem,
    UserItem,
    SharedFolderItem,
    MixerProperties,
)

register_factory, unregister_factory = bpy.utils.register_classes_factory(classes)


def register():
    register_factory()
    bpy.types.WindowManager.mixer = bpy.props.PointerProperty(type=MixerProperties)


def unregister():
    del bpy.types.WindowManager.mixer
    unregister_factory()
