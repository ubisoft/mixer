import bpy
import os
from .broadcaster import common


class RoomItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class UserItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class DCCSyncProperties(bpy.types.PropertyGroup):

    def on_user_selection_changed(self, context):
        # print("on_user_selection_changed", self.user_index)
        pass

    # host: bpy.props.StringProperty(name="Host", default="lgy-wks-052279")
    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=common.DEFAULT_PORT)
    room: bpy.props.StringProperty(name="Room", default=os.getlogin())
    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty()  # index in the list of rooms

    # User name as displayed in peers user list
    user: bpy.props.StringProperty(name="User", default=os.getlogin())

    # user list of the selected or connected room, according to status
    users: bpy.props.CollectionProperty(name="Users", type=UserItem)
    user_index: bpy.props.IntProperty(update=on_user_selection_changed)  # index in the list of users

    advanced: bpy.props.BoolProperty(default=False)
    remoteServerIsUp: bpy.props.BoolProperty(default=False)
    showServerConsole: bpy.props.BoolProperty(default=False)
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
