import bpy
from bpy.types import Operator

from mixer import display_version


class Mixer_OT_About(Operator):
    bl_idname = "mixer.about"
    bl_label = "About UAS Mixer..."
    bl_description = "More information about UAS Mixer..."
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        box = layout.box()

        # Version
        ###############
        row = box.row()
        row.separator()
        row.label(
            text=f"Version: {display_version or '(Unknown version)'}   -   ({'January 2021'})   -    Ubisoft Animation Studio"
        )

        # Authors
        ###############
        row = box.row()
        row.separator()
        row.label(text="Written by Philippe Crassous, Laurent Noel")

        # Purpose
        ###############
        row = box.row()
        row.label(text="Purpose:")
        row = box.row()
        row.separator()
        col = row.column()
        col.label(text="Mixer provides real time collaboration between several users of Blender,")
        col.label(text="allowing them to work on the same scene at the same time from")
        col.label(text="different computers.")

        # Dependencies
        ###############
        # row = box.row()
        # row.label(text="Dependencies:")
        # row = box.row()
        # row.separator()
        #
        # Documentation
        # ##############
        row = box.row()
        row.label(text="Documentation:")
        row = box.row()
        row.separator()
        row.operator(
            "mixer.open_documentation_url", text="Documentation, Download, Feedback..."
        ).path = "https://github.com/ubisoft/mixer#mixer"

        box.separator()

        layout.separator(factor=1)

    def execute(self, context):
        return {"FINISHED"}


_classes = (Mixer_OT_About,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
