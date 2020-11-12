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
This module define Blender Operators types for the addon.
"""

import logging
import os
import sys
import socket
import subprocess
import time

import bpy

from mixer.share_data import share_data
from mixer.bl_utils import get_mixer_props, get_mixer_prefs
from mixer.stats import save_statistics
from mixer.broadcaster.common import RoomAttributes, ClientAttributes
from mixer.connection import (
    is_client_connected,
    connect,
    join_room,
    leave_current_room,
    disconnect,
    network_consumer_timer,
)

logger = logging.getLogger(__name__)


poll_is_client_connected = (lambda: is_client_connected(), "Client not connected")
poll_already_in_a_room = (lambda: not share_data.client.current_room, "Already in a room")


def generic_poll(cls, context):
    for func, _reason in cls.poll_functors(context):
        if not func():
            return False
    return True


def generic_description(cls, context, properties):
    result = cls.__doc__
    for func, reason in cls.poll_functors(context):
        if not func():
            result += f" (Error: {reason})"
            break
    return result


class CreateRoomOperator(bpy.types.Operator):
    """Create a new room on Mixer server"""

    bl_idname = "mixer.create_room"
    bl_label = "Create Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll_functors(cls, context):
        return [
            poll_is_client_connected,
            poll_already_in_a_room,
            (lambda: get_mixer_prefs().room != "", "Room name cannot be empty"),
            (lambda: get_mixer_prefs().room not in share_data.client.rooms_attributes, "Room already exists"),
        ]

    @classmethod
    def poll(cls, context):
        return generic_poll(cls, context)

    @classmethod
    def description(cls, context, properties):
        return generic_description(cls, context, properties)

    def execute(self, context):
        assert share_data.client.current_room is None
        if not is_client_connected():
            return {"CANCELLED"}

        prefs = get_mixer_prefs()
        room = prefs.room
        logger.warning(f"CreateRoomOperator.execute({room})")
        join_room(room, prefs.vrtist_protocol)

        return {"FINISHED"}


def get_selected_room_dict():
    room_index = get_mixer_props().room_index
    assert room_index < len(get_mixer_props().rooms)
    return share_data.client.rooms_attributes[get_mixer_props().rooms[room_index].name]


class JoinRoomOperator(bpy.types.Operator):
    """Join a room"""

    bl_idname = "mixer.join_room"
    bl_label = "Join Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll_functors(cls, context):
        return [
            poll_is_client_connected,
            poll_already_in_a_room,
            (lambda: get_mixer_props().room_index < len(get_mixer_props().rooms), "Invalid room selection"),
            (
                lambda: (
                    ("vrtist_protocol" not in get_selected_room_dict() and not get_mixer_prefs().vrtist_protocol)
                    or (
                        "vrtist_protocol" in get_selected_room_dict()
                        and get_mixer_prefs().vrtist_protocol == get_selected_room_dict()["vrtist_protocol"]
                    )
                ),
                "vrtist_protocol flag does not match selected room",
            ),
            (
                lambda: get_selected_room_dict().get(RoomAttributes.JOINABLE, False),
                "Room is not joinable, first client has not finished sending initial content.",
            ),
        ]

    @classmethod
    def poll(cls, context):
        return generic_poll(cls, context)

    @classmethod
    def description(cls, context, properties):
        return generic_description(cls, context, properties)

    def execute(self, context):
        assert not share_data.client.current_room
        share_data.set_dirty()

        props = get_mixer_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        logger.warning(f"JoinRoomOperator.execute({room})")

        prefs = get_mixer_prefs()
        join_room(room, prefs.vrtist_protocol)

        return {"FINISHED"}


class DeleteRoomOperator(bpy.types.Operator):
    """Delete an empty room"""

    bl_idname = "mixer.delete_room"
    bl_label = "Delete Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        room_index = get_mixer_props().room_index
        return (
            is_client_connected()
            and room_index < len(get_mixer_props().rooms)
            and (get_mixer_props().rooms[room_index].users_count == 0)
        )

    def execute(self, context):
        props = get_mixer_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        share_data.client.delete_room(room)

        return {"FINISHED"}


class DownloadRoomOperator(bpy.types.Operator):
    """Download content of an empty room"""

    bl_idname = "mixer.download_room"
    bl_label = "Download Room"
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        room_index = get_mixer_props().room_index
        return (
            is_client_connected()
            and room_index < len(get_mixer_props().rooms)
            and (get_mixer_props().rooms[room_index].users_count == 0)
        )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from mixer.broadcaster.room_bake import download_room, save_room

        prefs = get_mixer_prefs()
        props = get_mixer_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        attributes, commands = download_room(prefs.host, prefs.port, room)
        save_room(attributes, commands, self.filepath)

        return {"FINISHED"}


class UploadRoomOperator(bpy.types.Operator):
    """Upload content of an empty room"""

    bl_idname = "mixer.upload_room"
    bl_label = "Upload Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        mixer_props = get_mixer_props()
        return (
            is_client_connected()
            and os.path.exists(mixer_props.upload_room_filepath)
            and mixer_props.upload_room_name not in share_data.client.rooms_attributes
        )

    def execute(self, context):
        from mixer.broadcaster.room_bake import load_room, upload_room

        prefs = get_mixer_prefs()
        props = get_mixer_props()

        attributes, commands = load_room(props.upload_room_filepath)
        upload_room(prefs.host, prefs.port, props.upload_room_name, attributes, commands)

        return {"FINISHED"}


class LeaveRoomOperator(bpy.types.Operator):
    """Leave the current room"""

    bl_idname = "mixer.leave_room"
    bl_label = "Leave Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return is_client_connected() and share_data.client.current_room is not None

    def execute(self, context):
        from mixer.bl_panels import update_ui_lists

        leave_current_room()
        update_ui_lists()
        return {"FINISHED"}


class ConnectOperator(bpy.types.Operator):
    """Connect to the Mixer server"""

    bl_idname = "mixer.connect"
    bl_label = "Connect to server"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return not is_client_connected()

    def execute(self, context):
        prefs = get_mixer_prefs()
        try:
            self.report({"INFO"}, f'Connecting to "{prefs.host}:{prefs.port}" ...')
            try:
                connect()
            except Exception as e:
                self.report({"ERROR"}, f"mixer.connect error : {e!r}")
                return {"CANCELLED"}

            self.report({"INFO"}, f'Connected to "{prefs.host}:{prefs.port}" ...')
        except socket.gaierror:
            msg = f'Cannot connect to "{prefs.host}": invalid host name or address'
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, repr(e))
            return {"CANCELLED"}

        return {"FINISHED"}


class DisconnectOperator(bpy.types.Operator):
    """Disconnect from the Mixer server"""

    bl_idname = "mixer.disconnect"
    bl_label = "Disconnect from server"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return is_client_connected()

    def execute(self, context):
        disconnect()
        self.report({"INFO"}, "Disconnected ...")
        return {"FINISHED"}


class LaunchVRtistOperator(bpy.types.Operator):
    """Launch a VRtist instance"""

    bl_idname = "vrtist.launch"
    bl_label = "Launch VRtist"
    bl_options = {"REGISTER"}

    vrtist_process = None

    @classmethod
    def poll(cls, context):
        # Check VRtist process to auto disconnect
        if cls.vrtist_process is not None and cls.vrtist_process.poll() is not None:
            cls.vrtist_process = None
            leave_current_room()
            disconnect()

        # Manage button state
        return os.path.isfile(get_mixer_prefs().VRtist)

    def execute(self, context):
        bpy.data.window_managers["WinMan"].mixer.send_base_meshes = False
        bpy.data.window_managers["WinMan"].mixer.send_bake_meshes = True

        mixer_prefs = get_mixer_prefs()
        if not share_data.client or not share_data.client.current_room:
            timeout = 10
            try:
                connect()
            except Exception as e:
                self.report({"ERROR"}, f"vrtist.launch connect error : {e!r}")
                return {"CANCELLED"}

            # Wait for local server creation
            while timeout > 0 and not is_client_connected():
                time.sleep(0.5)
                timeout -= 0.5
            if timeout <= 0:
                self.report({"ERROR"}, "vrtist.launch connect error : unable to connect")
                return {"CANCELLED"}

            logger.warning("LaunchVRtistOperator.execute({mixer_prefs.room})")
            join_room(mixer_prefs.room, True)

            # Wait for room creation/join
            timeout = 10
            while timeout > 0 and share_data.client.current_room is None:
                time.sleep(0.5)
                timeout -= 0.5
            if timeout <= 0:
                self.report({"ERROR"}, "vrtist.launch connect error : unable to join room")
                return {"CANCELLED"}

            # Wait for client id
            timeout = 10
            while timeout > 0 and share_data.client.client_id is None:
                network_consumer_timer()
                time.sleep(0.1)
                timeout -= 0.1
            if timeout <= 0:
                self.report({"ERROR"}, "vrtist.launch connect error : unable to retrieve client id")
                return {"CANCELLED"}

        color = share_data.client.clients_attributes[share_data.client.client_id].get(
            ClientAttributes.USERCOLOR, (0.0, 0.0, 0.0)
        )
        color = (int(c * 255) for c in color)
        color = "#" + "".join(f"{c:02x}" for c in color)
        name = "VR " + share_data.client.clients_attributes[share_data.client.client_id].get(
            ClientAttributes.USERNAME, "client"
        )

        args = [
            mixer_prefs.VRtist,
            "--room",
            share_data.client.current_room,
            "--hostname",
            mixer_prefs.host,
            "--port",
            str(mixer_prefs.port),
            "--master",
            str(share_data.client.client_id),
            "--usercolor",
            color,
            "--username",
            name,
        ]
        LaunchVRtistOperator.vrtist_process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False
        )
        return {"FINISHED"}


class WriteStatisticsOperator(bpy.types.Operator):
    """Write Mixer statistics in a file"""

    bl_idname = "mixer.write_statistics"
    bl_label = "Mixer Write Statistics"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if share_data.current_statistics is not None:
            save_statistics(share_data.current_statistics, get_mixer_props().statistics_directory)
        return {"FINISHED"}


class OpenStatsDirOperator(bpy.types.Operator):
    """Write Mixer stats directory in explorer"""

    bl_idname = "mixer.open_stats_dir"
    bl_label = "Mixer Open Stats Directory"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if sys.platform == "win32":
            os.startfile(get_mixer_prefs().statistics_directory)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, get_mixer_prefs().statistics_directory])
        return {"FINISHED"}


classes = (
    LaunchVRtistOperator,
    CreateRoomOperator,
    ConnectOperator,
    DisconnectOperator,
    JoinRoomOperator,
    DeleteRoomOperator,
    LeaveRoomOperator,
    WriteStatisticsOperator,
    OpenStatsDirOperator,
    DownloadRoomOperator,
    UploadRoomOperator,
)

register_factory, unregister_factory = bpy.utils.register_classes_factory(classes)


def register():
    register_factory()


def unregister():
    disconnect()
    unregister_factory()
