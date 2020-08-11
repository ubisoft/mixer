"""
Utility functions that may require os/platform specific adjustments
"""

import getpass
import os


def getuser() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.getlogin()
