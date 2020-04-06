from . import ui
from . import operators
from . import data
from . import stats
from .shareData import shareData
import bpy
import atexit
import logging
from pathlib import Path

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
MODULE_PATH = Path(__file__).parent


def cleanup():
    shareData = operators.shareData
    if None is shareData.current_statistics and shareData.auto_save_statistics:
        stats.save_statistics(shareData.current_statistics, shareData.statistics_directory)
    try:
        if shareData.localServerProcess:
            shareData.localServerProcess.kill()
    except Exception:
        pass


class Formatter(logging.Formatter):
    def __init__(self, fmt):
        super().__init__(fmt)

    def format(self, record: logging.LogRecord):
        """
        The role of this custom formatter is:
        - append filepath and lineno to logging format but shorten path to files, to make logs more clear
        - to append "./" at the begining to permit going to the line quickly with VS Code CTRL+click from terminal
        """
        s = super().format(record)
        pathname = Path(record.pathname).relative_to(MODULE_PATH)
        s += f" [./{pathname}:{record.lineno}]"
        return s


def register():
    if len(logger.handlers) == 0:
        logger.setLevel(logging.WARNING)
        formatter = Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        handler = logging.FileHandler(data.get_log_file())
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    operators.register()
    ui.register()
    data.register()

    atexit.register(cleanup)


def unregister():
    operators.disconnect()

    if shareData:
        if shareData.client and bpy.app.timers.is_registered(shareData.client.networkConsumer):
            bpy.app.timers.unregister(shareData.client.networkConsumer)

    operators.unregister()
    ui.unregister()
    data.unregister()

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
