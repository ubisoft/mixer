import sys
import os
import bpy
import time
sys.path.append(os.getcwd())  # nopep8
from tests import utils  # nopep8


def get_dcc_sync_props():
    return bpy.context.window_manager.dcc_sync


print('Before')
utils.connect()
utils.join()


bpy.ops.wm.save_as_mainfile(filepath='f2.blend')
utils.disconnect()


# https://blender.stackexchange.com/questions/7484/get-a-diff-between-two-blend-files


print('After')
