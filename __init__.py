from . import ui
from . import operators
from . import data
import bpy
import atexit
import logging

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
    bpy.ops.dcc_sync.update_room_list()
    return None


def cleanup():
    try:
        if operators.shareData.localServerProcess:
            operators.shareData.localServerProcess.kill()
    except Exception:
        pass


def register():
    logger = logging.getLogger(__package__)
    if len(logger.handlers) == 0:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    operators.register()
    ui.register()
    data.register()

    bpy.app.timers.register(refreshRoomListHack, first_interval=0)
    atexit.register(cleanup)


def unregister():
    operators.unregister()
    ui.unregister()
    data.unregister()

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
