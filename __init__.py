from . import ui
from . import operators
import bpy
import atexit

bl_info = {
    "name": "VRtist",
    "author": "Ubisoft",
    "description": "VR manipultation",
    "blender": (2, 80, 0),
    "location": "",
    "warning": "",
    "category": "Generic"
}


def refreshRoomListHack():
    bpy.ops.scene.vrtistroomlistupdate()
    return None


def cleanup():
    try:
        if operators.shareData.localServerProcess:
            operators.shareData.localServerProcess.kill()
    except Exception:
        pass


def register():
    operators.register()
    ui.register()

    bpy.types.Scene.vrtistconnect = bpy.props.PointerProperty(type=operators.VRtistConnectProperties)

    bpy.app.timers.register(refreshRoomListHack, first_interval=0)
    atexit.register(cleanup)


def unregister():
    operators.unregister()
    ui.unregister()

    del bpy.types.Scene.vrtistconnect

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
