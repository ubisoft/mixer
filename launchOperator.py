import bpy
import subprocess
import os

class VRtistProperties(bpy.types.PropertyGroup):
    VRtist: bpy.props.StringProperty(name="VRtist", default="D:/unity/VRtist/Build/VRtist.exe")
    Exchange: bpy.props.StringProperty(name="Exchange", default="D:/unity/VRtist/Build/tmp")

class VRtistOperator(bpy.types.Operator):
    bl_idname = "scene.vrtist"
    bl_label = "VRtist"
    bl_options = {'REGISTER', 'UNDO'}
    
    #vrtist = bpy.data.scenes[0].vrtist.VRtist
    
    def execute(self, context):
        FNULL = open(os.devnull, 'w')
        args = bpy.data.scenes[0].vrtist.VRtist
        subprocess.Popen(args, stdout=FNULL, stderr=FNULL, shell=False)

        #os.system(bpy.data.scenes[0].vrtist.VRtist)
        return {'FINISHED'}        

def menu_func(self, context):
    self.layout.operator(VRtistOperator.bl_idname)
