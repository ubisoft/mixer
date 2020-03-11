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

# load file

utils.join()
time.sleep(10)


for obj in bpy.context.scene.objects:
    if obj.type == 'MESH' and obj.name == 'Cube':
        obj.name = 'cube__'


bpy.ops.wm.save_as_mainfile(filepath='f1.blend')
# freezes, of course
time.sleep(1000)
utils.disconnect()

# https://blender.stackexchange.com/questions/15670/send-instructions-to-blender-from-external-application
# https://blender.stackexchange.com/questions/7484/get-a-diff-between-two-blend-files


print('After')
