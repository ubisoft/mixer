# import os
import shutil
import bpy

zip_name = shutil.make_archive("dccsync_unittest", "zip", ".", "dccsync")
bpy.ops.preferences.addon_install(overwrite=True, filepath=zip_name)
bpy.ops.preferences.addon_enable(module="dccsync")
try:
    pass
    # os.remove(zip_name)
except Exception:
    pass
