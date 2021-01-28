import os
from pathlib import Path
import subprocess


import bpy
from bpy.types import Operator
from bpy.props import StringProperty


class Mixer_OT_Open_Documentation_Url(Operator):
    bl_idname = "mixer.open_documentation_url"
    bl_label = "Open Documentation Web Page"
    bl_description = "Open documentation.\nShift + Click: Copy the URL into the clipboard"

    path: StringProperty()

    def invoke(self, context, event):
        if event.shift:
            # copy path to clipboard
            cmd = "echo " + (self.path).strip() + "|clip"
            subprocess.check_call(cmd, shell=True)
        else:
            subprocess.Popen(f'explorer "{self.path}"')

        return {"FINISHED"}


_classes = (Mixer_OT_Open_Documentation_Url,)


def register():

    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)