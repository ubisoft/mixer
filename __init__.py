from . import ui
from . import operators
from . import data
from . import stats
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
    shareData = operators.shareData
    if None != shareData.current_statistics and shareData.auto_save_statistics:
        stats.save_statistics(shareData.current_statistics, shareData.statistics_directory)
    try:
        if shareData.localServerProcess:
            shareData.localServerProcess.kill()
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
    operators.leave_current_room()

    if bpy.app.timers.is_registered(refreshRoomListHack):
        bpy.app.timers.unregister(refreshRoomListHack)

    shareData = operators.shareData
    if shareData:
        if shareData.client and bpy.app.timers.is_registered(shareData.client.networkConsumer):
            bpy.app.timers.unregister(shareData.client.networkConsumer)

        if shareData.roomListUpdateClient and bpy.app.timers.is_registered(shareData.roomListUpdateClient.networkConsumer):
            bpy.app.timers.unregister(shareData.roomListUpdateClient.networkConsumer)

    operators.unregister()
    ui.unregister()
    data.unregister()

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
