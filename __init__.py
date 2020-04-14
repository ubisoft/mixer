from . import ui
from . import operators
from . import data
from . import stats
from .share_data import share_data
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
    "category": "Generic",
}

logger = logging.getLogger(__name__)
MODULE_PATH = Path(__file__).parent


def cleanup():
    if share_data.current_statistics is not None and share_data.auto_save_statistics:
        stats.save_statistics(share_data.current_statistics, share_data.statistics_directory)
    try:
        if share_data.localServerProcess:
            share_data.localServerProcess.kill()
    except Exception:
        pass


class Formatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        formatter = Formatter("{asctime} - {name:<36} - {levelname:<8} - {message:<80}", style="{")
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
    operators.unregister()
    ui.unregister()
    data.unregister()

    cleanup()
    atexit.unregister(cleanup)


if __name__ == "__main__":
    register()
