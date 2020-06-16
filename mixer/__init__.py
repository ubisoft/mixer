import atexit
import logging
from pathlib import Path

bl_info = {
    "name": "Mixer",
    "author": "Ubisoft Animation Studio",
    "description": "Collaborative 3D edition accross 3D Softwares",
    "version": (0, 3, 1),
    "blender": (2, 82, 0),
    "location": "",
    "warning": "Experimental addon, can break your scenes",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Collaboration",
}

logger = logging.getLogger(__name__)
MODULE_PATH = Path(__file__).parent.parent


def cleanup():
    from mixer import stats
    from mixer.share_data import share_data

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
        s += f" [.\\{pathname}:{record.lineno}]"
        return s


def register():
    from mixer import ui
    from mixer import operators
    from mixer import data
    from mixer.blender_data import debug_addon

    if len(logger.handlers) == 0:
        logger.setLevel(logging.WARNING)
        formatter = Formatter("{asctime} {levelname[0]} {name:<36}  - {message:<80}", style="{")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        handler = logging.FileHandler(data.get_log_file())
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    operators.register()
    ui.register()
    data.register()
    debug_addon.register()

    atexit.register(cleanup)


def unregister():
    from mixer import ui
    from mixer import operators
    from mixer import data
    from mixer.blender_data import debug_addon

    operators.unregister()
    ui.unregister()
    data.unregister()
    debug_addon.unregister()

    cleanup()
    atexit.unregister(cleanup)
