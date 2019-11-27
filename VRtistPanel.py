import bpy

class VRtistPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "VRtist Panel"
    bl_idname = "OBJECT_PT_vrtist"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        row = layout.row()
        row.label(text="VRtist", icon='SCENE_DATA')

        row = layout.column()
        row.prop(scene.vrtistconnect, "host", text="Hostname")
        row.prop(scene.vrtistconnect, "port", text="Port")                
        row.operator("scene.vrtistconnect", text="Connect")

        row.prop(scene.vrtist, "VRtist", text="VRtist Path")
        row.prop(scene.vrtist, "Exchange", text="Exchange Path")
        row.operator("scene.vrtist", text="Link with VRTist")
