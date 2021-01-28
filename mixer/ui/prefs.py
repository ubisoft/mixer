import bpy
from bpy.types import Menu


#############
# Preferences
#############


class MIXER_MT_Prefs_Main_Menu(Menu):
    bl_idname = "MIXER_MT_prefs_main_menu"
    bl_label = "Mixer Settings"

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.operator("preferences.addon_show", text="Add-on Preferences...").module = "mixer"

        layout.separator()
        row = layout.row(align=True)
        row.operator("uas_shot_manager.general_prefs")
        row = layout.row(align=True)
        row.operator("uas_shot_manager.project_settings_prefs")

        layout.separator()
        row = layout.row(align=True)
        row.operator(
            "mixer.open_documentation_url", text="Documentation"
        ).path = "https://github.com/ubisoft/mixer#mixer"

        layout.separator()
        row = layout.row(align=True)
        row.operator("mixer.about", text="About...")


_classes = (MIXER_MT_Prefs_Main_Menu,)


def register():

    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
