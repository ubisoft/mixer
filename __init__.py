import bpy

bl_info = {
    "name" : "VRtist",
    "author" : "Ubisoft",
    "description" : "VR manipultation",
    "blender" : (2 ,80, 0),
    "location" : "",
    "warning" : "",
    "category" : "Generic"
}

from . import launchOperator
from . import connectOperator
from . import VRtistPanel

def register():    
    bpy.utils.register_class(launchOperator.VRtistOperator)
    bpy.utils.register_class(launchOperator.VRtistProperties)
    bpy.utils.register_class(connectOperator.VRtistConnectOperator)
    bpy.utils.register_class(connectOperator.VRtistConnectProperties)
    bpy.types.Scene.vrtist = bpy.props.PointerProperty(type=launchOperator.VRtistProperties)
    bpy.types.Scene.vrtistconnect = bpy.props.PointerProperty(type=connectOperator.VRtistConnectProperties)
    bpy.utils.register_class(VRtistPanel.VRtistPanel)

    
def unregister():
    bpy.utils.unregister_class(VRtistPanel.VRtistPanel)
    del bpy.types.Scene.vrtistconnect
    del bpy.types.Scene.vrtist
    bpy.utils.unregister_class(connectOperator.VRtistConnectProperties)
    bpy.utils.unregister_class(connectOperator.VRtistConnectOperator)
    bpy.utils.unregister_class(launchOperator.VRtistProperties)
    bpy.utils.unregister_class(launchOperator.VRtistOperator)
    
if __name__ == "__main__":
    register()
