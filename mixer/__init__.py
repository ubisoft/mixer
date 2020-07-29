import atexit
import faulthandler
import logging
import os
from pathlib import Path
from typing import Dict, Any

bl_info: Dict[str, Any] = {
    "name": "Mixer",
    "author": "Ubisoft Animation Studio",
    "description": "Collaborative 3D edition accross 3D Softwares",
    "version": (0, 12, 0),
    "blender": (2, 82, 0),
    "location": "",
    "warning": "Experimental addon, can break your scenes",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Collaboration",
}

__version__ = f"v{bl_info['version'][0]}.{bl_info['version'][1]}.{bl_info['version'][2]}"

logger = logging.getLogger(__name__)
logger.propagate = False
MODULE_PATH = Path(__file__).parent.parent
_disable_fault_handler = False


def cleanup():
    from mixer import stats
    from mixer.share_data import share_data

    if share_data.current_statistics is not None and share_data.auto_save_statistics:
        stats.save_statistics(share_data.current_statistics, share_data.statistics_directory)
    try:
        if share_data.local_server_process:
            share_data.local_server_process.kill()
    except Exception:
        pass

    if _disable_fault_handler:
        faulthandler.disable()


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
        s += f" [{os.curdir}{os.sep}{pathname}:{record.lineno}]"
        return s


def get_logs_directory():
    def _get_logs_directory():
        import tempfile

        if "MIXER_USER_LOGS_DIR" in os.environ:
            username = os.getlogin()
            base_shared_path = Path(os.environ["MIXER_USER_LOGS_DIR"])
            if os.path.exists(base_shared_path):
                return os.path.join(os.fspath(base_shared_path), username)
            logger.error(
                f"MIXER_USER_LOGS_DIR env var set to {base_shared_path}, but directory does not exists. Falling back to default location."
            )
        return os.path.join(os.fspath(tempfile.gettempdir()), "mixer")

    dir = _get_logs_directory()
    if not os.path.exists(dir):
        os.makedirs(dir)
    return dir


def get_log_file():
    from mixer.share_data import share_data

    return os.path.join(get_logs_directory(), f"mixer_logs_{share_data.run_id}.log")


def register():
    from mixer import ui
    from mixer import operators
    from mixer import bl_properties, bl_preferences
    from mixer.blender_data import debug_addon

    if len(logger.handlers) == 0:
        logger.setLevel(logging.WARNING)
        formatter = Formatter("{asctime} {levelname[0]} {name:<36}  - {message:<80}", style="{")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        handler = logging.FileHandler(get_log_file())
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if not faulthandler.is_enabled():
        faulthandler.enable()
        global _disable_fault_handler
        _disable_fault_handler = True

    debug_addon.register()

    bl_preferences.register()
    bl_properties.register()
    ui.register()
    operators.register()

    atexit.register(cleanup)


def unregister():
    from mixer import ui
    from mixer import operators
    from mixer import bl_properties, bl_preferences
    from mixer.blender_data import debug_addon

    cleanup()

    atexit.unregister(cleanup)

    operators.unregister()
    ui.unregister()
    bl_properties.unregister()
    bl_preferences.unregister()

    debug_addon.unregister()
