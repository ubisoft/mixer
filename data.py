import bpy
import os
import logging
from .broadcaster import common
from .shareData import shareData


class RoomItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class UserItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class DCCSyncProperties(bpy.types.PropertyGroup):

    def on_user_selection_changed(self, context):
        print("on_user_selection_changed", self.user_index)

    def on_room_selection_changed(self, context):
        self.updateListUsersProperty()

    def updateListUsersProperty(self):
        self.users.clear()
        if shareData.client_ids is None:
            return

        if shareData.currentRoom:
            room_name = shareData.currentRoom
        else:
            idx = self.room_index
            if idx >= len(self.rooms):
                return
            room_name = self.rooms[idx].name

        client_ids = [c for c in shareData.client_ids if c['room'] == room_name]

        for client in client_ids:
            item = self.users.add()
            display_name = client['name']
            display_name = display_name if display_name is not None else "<unnamed>"
            display_name = f"{display_name} ({client['ip']}:{client['port']})"
            item.name = display_name

    def updateListRoomsProperty(self):
        self.rooms.clear()
        if shareData.client_ids is None:
            return

        rooms = {id['room'] for id in shareData.client_ids if id['room']}
        for room in rooms:
            item = self.rooms.add()
            item.name = room

    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=common.DEFAULT_PORT)
    room: bpy.props.StringProperty(name="Room", default=os.getlogin())
    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty(update=on_room_selection_changed)  # index in the list of rooms

    # User name as displayed in peers user list
    user: bpy.props.StringProperty(name="User", default=os.getlogin())

    # user list of the selected or connected room, according to status
    users: bpy.props.CollectionProperty(name="Users", type=UserItem)
    user_index: bpy.props.IntProperty(update=on_user_selection_changed)  # index in the list of users

    advanced: bpy.props.BoolProperty(default=False)
    remoteServerIsUp: bpy.props.BoolProperty(default=False)

    show_server_console_value = common.is_debugger_attached()
    logging.info("Debugger attached : %s ", show_server_console_value)
    showServerConsole: bpy.props.BoolProperty(default=show_server_console_value)

    VRtist: bpy.props.StringProperty(name="VRtist", default=os.environ.get(
        "VRTIST_EXE", "D:/unity/VRtist/Build/VRtist.exe"))


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
