import bpy

import os
from pathlib import Path
import bpy.utils.previews


def init_global_variables():

    # icons ############
    global icons_col

    pcoll = bpy.utils.previews.new()
    my_icons_dir = os.path.join(os.path.dirname(__file__), "./icons")
    for png in Path(my_icons_dir).rglob("*.png"):
        pcoll.load(png.stem, str(png), "IMAGE")

    icons_col = pcoll


def release_global_variables():

    global icons_col

    bpy.utils.previews.remove(icons_col)
    icons_col = None
