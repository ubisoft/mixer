# import os
import shutil
import bpy

zip_name = shutil.make_archive("mixer_unittest", "zip", ".", "mixer")
bpy.ops.preferences.addon_install(overwrite=True, filepath=zip_name)
bpy.ops.preferences.addon_enable(module="mixer")
try:
    pass
    # os.remove(zip_name)
except Exception:
    pass
