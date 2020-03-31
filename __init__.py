from . import ui
from . import operators
from . import data
from . import stats
from .shareData import shareData
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

logger = logging.getLogger(__name__)


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
    if len(logger.handlers) == 0:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s [ %(pathname)s:%(lineno)d ]'))

    operators.register()
    ui.register()
    data.register()

    atexit.register(cleanup)


def unregister():
    operators.leave_current_room()

    if shareData:
        if shareData.client and bpy.app.timers.is_registered(shareData.client.networkConsumer):
            bpy.app.timers.unregister(shareData.client.networkConsumer)
    operators.disconnect()

    operators.unregister()
    ui.unregister()
    data.unregister()

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
