import logging
import os
import socket
import subprocess

import bpy

from mixer.share_data import share_data
from mixer.bl_utils import get_mixer_props, get_mixer_prefs
from mixer.stats import save_statistics
from mixer.broadcaster.common import RoomAttributes
from mixer.connection import is_client_connected, connect, join_room, leave_current_room, disconnect

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

        join_room(get_mixer_prefs().room)

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
                    ("experimental_sync" not in get_selected_room_dict() and not get_mixer_prefs().experimental_sync)
                    or (
                        "experimental_sync" in get_selected_room_dict()
                        and get_mixer_prefs().experimental_sync == get_selected_room_dict()["experimental_sync"]
                    )
                ),
                "Experimental flag does not match selected room",
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
        join_room(room)

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
        from mixer import ui

        leave_current_room()
        ui.update_ui_lists()
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
            if not connect():
                self.report({"ERROR"}, "unknown error")
                return {"CANCELLED"}

            self.report({"INFO"}, f'Connected to "{prefs.host}:{prefs.port}" ...')
        except socket.gaierror as e:
            msg = f'Cannot connect to "{prefs.host}": invalid host name or address'
            self.report({"ERROR"}, msg)
            if prefs.env != "production":
                raise e
        except Exception as e:
            self.report({"ERROR"}, repr(e))
            if prefs.env != "production":
                raise e
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

    @classmethod
    def poll(cls, context):
        return os.path.isfile(get_mixer_prefs().VRtist)

    def execute(self, context):
        bpy.data.window_managers["WinMan"].mixer.send_base_meshes = False
        mixer_prefs = get_mixer_prefs()
        if not share_data.client.current_room:
            if not connect():
                return {"CANCELLED"}
            join_room(mixer_prefs.room)

        args = [
            mixer_prefs.VRtist,
            "--room",
            share_data.client.current_room,
            "--hostname",
            mixer_prefs.host,
            "--port",
            str(mixer_prefs.port),
        ]
        subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
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
        os.startfile(get_mixer_prefs().statistics_directory)
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
