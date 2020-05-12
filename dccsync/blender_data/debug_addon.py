import bpy
import logging
import dccsync.blender_data.blenddata
from dccsync.blender_data.blenddata import collection_name_to_type

default_test = ""
logger = logging.Logger(__name__, logging.INFO)


class DebugDataProperties(bpy.types.PropertyGroup):
    test_names: bpy.props.StringProperty(name="TestNames", default=default_test)


class BuildProxyOperator(bpy.types.Operator):
    """Build proxy from current file"""

    bl_idname = "dcc_sync.build_proxy"
    bl_label = "DCCSync build proxy"
    bl_options = {"REGISTER"}

    def execute(self, context):
        # Cannot import at module level, since it requires access to bpy.data which is not
        # accessible during module load
        from dccsync.blender_data.proxy import BpyBlendProxy
        from dccsync.blender_data.filter import default_context

        proxy = BpyBlendProxy()
        proxy.load(default_context)

        non_empty = proxy.get_non_empty_collections()
        logger.info(f"Number of non empty collections in proxy: {len(non_empty)}")

        # Put breakpoint here and examinate non_empty dictionnary
        return {"FINISHED"}


class DebugDataTestOperator(bpy.types.Operator):
    """Execute blender_data tests for debugging"""

    bl_idname = "dcc_sync.data_test"
    bl_label = "DCCSync test data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        # Cannot import at module level, since it requires access to bpy.data which is not
        # accessible during module load
        from dccsync.blender_data.tests.test_for_debug import run_tests

        test_names = "dccsync.blender_data.tests.test_for_debug"
        names = get_props().test_names
        if names:
            test_names = test_names + "." + names
        run_tests(test_names)
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
        row.operator(BuildProxyOperator.bl_idname, text="Build Proxy")
        row.operator(DebugDataTestOperator.bl_idname, text="Test")
        row = layout.row()
        row.prop(get_props(), "test_names", text="Test names")


classes = (
    BuildProxyOperator,
    DebugDataTestOperator,
    DebugDataPanel,
    DebugDataProperties,
)


def get_props() -> DebugDataProperties:
    return bpy.context.window_manager.debug_data_props


def register():
    for t in collection_name_to_type.values():
        t.dccsync_uuid = bpy.props.StringProperty(default="")

    for class_ in classes:
        bpy.utils.register_class(class_)
    bpy.types.WindowManager.debug_data_props = bpy.props.PointerProperty(type=DebugDataProperties)
    bpy.app.handlers.load_post.append(dccsync.blender_data.blenddata.on_load)


def unregister():
    for class_ in classes:
        bpy.utils.unregister_class(class_)
    bpy.app.handlers.load_post.remove(dccsync.blender_data.blenddata.on_load)
