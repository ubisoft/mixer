
import bpy


class DebugDataOperator(bpy.types.Operator):
    """Execute blender_data tests for debugging"""

    bl_idname = "dcc_sync.data"
    bl_label = "DCCSync test data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from dccsync.blender_data.test_for_debug import main
        main()
        return {"FINISHED"}


class DebugDataPanel(bpy.types.Panel):
    """blender_data debug Panel"""

    bl_label = "Data"
    bl_idname = "DATA_PT_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DCC Sync"

    def draw(self, context):
        layout = self.layout

        row = layout.column()
        row.operator(DebugDataOperator.bl_idname, text="Data")


classes = (DebugDataOperator, DebugDataPanel)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():

    for _ in classes:
        bpy.utils.unregister_class(_)
