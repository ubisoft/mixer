import bpy
from .proxy import BpyBlendProxy, data_types
from .diff import BpyBlendDiff

proxy = BpyBlendProxy()
deltas = BpyBlendDiff()


class DebugDataLoadOperator(bpy.types.Operator):
    """Execute blender_data tests for debugging"""

    bl_idname = "dcc_sync.data_load"
    bl_label = "DCCSync test data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        proxy.load()
        return {"FINISHED"}


class DebugDataDiffOperator(bpy.types.Operator):
    """Execute blender_data tests for debugging"""

    bl_idname = "dcc_sync.data_diff"
    bl_label = "DCCSync test data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        deltas.diff(proxy)
        return {"FINISHED"}


class DebugDataUpdateOperator(bpy.types.Operator):
    """Execute blender_data tests for debugging"""

    bl_idname = "dcc_sync.data_update"
    bl_label = "DCCSync test data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        proxy.update(deltas)
        return {"FINISHED"}


class DebugDataTestOperator(bpy.types.Operator):
    """Execute blender_data tests for debugging"""

    bl_idname = "dcc_sync.data_test"
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
        row.operator(DebugDataLoadOperator.bl_idname, text="Load")
        row.operator(DebugDataDiffOperator.bl_idname, text="Diff")
        row.operator(DebugDataUpdateOperator.bl_idname, text="Update")
        row.operator(DebugDataTestOperator.bl_idname, text="Test")


classes = (DebugDataLoadOperator, DebugDataDiffOperator, DebugDataUpdateOperator, DebugDataTestOperator, DebugDataPanel)


def register():
    for t in data_types.values():
        t.dccsync_uuid = bpy.props.StringProperty(default="")
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():

    for _ in classes:
        bpy.utils.unregister_class(_)
