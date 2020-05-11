import bpy
import dccsync.blender_data.blenddata

data_types = {
    "actions": bpy.types.Action,
    "armatures": bpy.types.Armature,
    "brushes": bpy.types.Brush,
    "cache_files": bpy.types.CacheFile,
    "cameras": bpy.types.Camera,
    "collections": bpy.types.Collection,
    "curves": bpy.types.Curve,
    "fonts": bpy.types.VectorFont,
    "grease_pencils": bpy.types.GreasePencil,
    "images": bpy.types.Image,
    "lattices": bpy.types.Lattice,
    "libraries": bpy.types.Library,
    "lightprobess": bpy.types.LightProbe,
    "lights": bpy.types.Light,
    "linestyles": bpy.types.FreestyleLineStyle,
    "masks": bpy.types.Mask,
    "materials": bpy.types.Material,
    "meshes": bpy.types.Mesh,
    "metaballs": bpy.types.MetaBall,
    "moveclips": bpy.types.MovieClip,
    "node_groups": bpy.types.NodeTree,
    "objects": bpy.types.Object,
    "paint_curves": bpy.types.PaintCurve,
    "palettes": bpy.types.Palette,
    "particles": bpy.types.ParticleSettings,
    "scenes": bpy.types.Scene,
    "screens": bpy.types.Screen,
    "shape_keys": bpy.types.Key,
    "sounds": bpy.types.Sound,
    "speakers": bpy.types.Speaker,
    "texts": bpy.types.Text,
    "textures": bpy.types.Texture,
    "window_managers": bpy.types.WindowManager,
    "worlds": bpy.types.World,
    "workspaces": bpy.types.WorkSpace,
}

default_test = ""


class DebugDataProperties(bpy.types.PropertyGroup):
    test_names: bpy.props.StringProperty(name="TestNames", default=default_test)


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
        row.operator(DebugDataTestOperator.bl_idname, text="Test")
        row = layout.row()
        row.prop(get_props(), "test_names", text="Test names")


classes = (
    DebugDataTestOperator,
    DebugDataPanel,
    DebugDataProperties,
)


def get_props() -> DebugDataProperties:
    return bpy.context.window_manager.debug_data_props


def register():
    for t in data_types.values():
        t.dccsync_uuid = bpy.props.StringProperty(default="")

    for class_ in classes:
        bpy.utils.register_class(class_)
    bpy.types.WindowManager.debug_data_props = bpy.props.PointerProperty(type=DebugDataProperties)
    bpy.app.handlers.load_post.append(dccsync.blender_data.blenddata.on_load)


def unregister():
    for class_ in classes:
        bpy.utils.unregister_class(class_)
    bpy.app.handlers.load_post.remove(dccsync.blender_data.blenddata.on_load)
