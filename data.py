import bpy
import os
from .broadcaster import common


def get_dcc_sync_props():
    return bpy.context.window_manager.dcc_sync


class RoomItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")


class DCCSyncProperties(bpy.types.PropertyGroup):
    #host: bpy.props.StringProperty(name="Host", default="lgy-wks-052279")
    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=common.DEFAULT_PORT)
    room: bpy.props.StringProperty(name="Room", default=os.getlogin())
    rooms: bpy.props.CollectionProperty(name="Rooms", type=RoomItem)
    room_index: bpy.props.IntProperty()  # index in the list of rooms
    advanced: bpy.props.BoolProperty(default=False)
    remoteServerIsUp: bpy.props.BoolProperty(default=False)
    VRtist: bpy.props.StringProperty(name="VRtist", default=os.environ.get(
        "VRTIST_EXE", "D:/unity/VRtist/Build/VRtist.exe"))


classes = (
    RoomItem,
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
