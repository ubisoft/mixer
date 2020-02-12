from . import VRtistPanel
from . import vrtistOperators
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
        if vrtistOperators.shareData.localServerProcess:
            vrtistOperators.shareData.localServerProcess.kill()
    except Exception:
        pass


def register():
    vrtistOperators.register()
    VRtistPanel.register()

    bpy.types.Scene.vrtistconnect = bpy.props.PointerProperty(type=vrtistOperators.VRtistConnectProperties)

    bpy.app.timers.register(refreshRoomListHack, first_interval=0)
    atexit.register(cleanup)


def unregister():
    vrtistOperators.unregister()
    VRtistPanel.unregister()

    del bpy.types.Scene.vrtistconnect

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
