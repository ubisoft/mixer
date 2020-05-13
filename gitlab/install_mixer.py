# import os
import shutil
import bpy
import os
from pathlib import Path

src_dir = Path(__file__).parent.parent

zip_basename = Path(__file__).parent / "blender" / "mixer_unittest"
if os.path.exists(str(zip_basename) + ".zip"):
    os.remove(str(zip_basename) + ".zip")

zip_name = shutil.make_archive(zip_basename, "zip", src_dir, "mixer")

bpy.ops.preferences.addon_install(overwrite=True, filepath=zip_name)
bpy.ops.preferences.addon_enable(module="mixer")
