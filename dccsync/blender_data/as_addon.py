
import bpy


class DataOperator(bpy.types.Operator):
    """Write dccsync stats directory in explorer"""

    bl_idname = "dcc_sync.data"
    bl_label = "DCCSync test data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from dccsync.blender_data.test1 import main
        main()
        return {"FINISHED"}

class USERS_UL_ItemRenderer(bpy.types.UIList):  # noqa
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.row()
        split.label(text=item.name)  # avoids renaming the item by accident


class DataPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""

    bl_label = "Data"
    bl_idname = "DATA_PT_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DCC Sync"

    def draw(self, context):
        layout = self.layout

        row = layout.column()
        row.operator(DataOperator.bl_idname, text="Data")


classes = (DataOperator, DataPanel)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():

    for _ in classes:
        bpy.utils.unregister_class(_)
