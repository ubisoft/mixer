import bpy
import atexit

bl_info = {
    "name" : "VRtist",
    "author" : "Ubisoft",
    "description" : "VR manipultation",
    "blender" : (2 ,80, 0),
    "location" : "",
    "warning" : "",
    "category" : "Generic"
}

from . import vrtistOperators
from . import VRtistPanel

def refreshRoomListHack():
    bpy.ops.scene.vrtistroomlistupdate()
    return None

def cleanup():
    try:
        if vrtistOperators.shareData.localServerProcess:
            vrtistOperators.shareData.localServerProcess.kill()
    except Exception:
        pass

def register():    

    bpy.utils.register_class(vrtistOperators.ROOM_UL_ItemRenderer)
    bpy.utils.register_class(vrtistOperators.VRtistOperator)
    bpy.utils.register_class(vrtistOperators.VRtistProperties)
    bpy.utils.register_class(vrtistOperators.VRtistRoomItem)
    bpy.utils.register_class(vrtistOperators.VRtistConnectProperties)
    bpy.utils.register_class(vrtistOperators.VRtistCreateRoomOperator)
    bpy.utils.register_class(vrtistOperators.VRtistRoomListUpdateOperator)
    bpy.utils.register_class(vrtistOperators.VRtistSendSelectionOperator)
    bpy.utils.register_class(vrtistOperators.VRtistJoinRoomOperator)
    bpy.types.Scene.vrtist = bpy.props.PointerProperty(type=vrtistOperators.VRtistProperties)
    bpy.types.Scene.vrtistconnect = bpy.props.PointerProperty(type=vrtistOperators.VRtistConnectProperties)
    bpy.utils.register_class(VRtistPanel.VRtistPanel)

    bpy.app.timers.register(refreshRoomListHack, first_interval=0)
    atexit.register(cleanup)
    
def unregister():
    bpy.utils.unregister_class(VRtistPanel.VRtistPanel)
    del bpy.types.Scene.vrtistconnect
    del bpy.types.Scene.vrtist
    bpy.utils.unregister_class(vrtistOperators.VRtistSendSelectionOperator)
    bpy.utils.unregister_class(vrtistOperators.VRtistConnectProperties)
    bpy.utils.unregister_class(vrtistOperators.VRtistCreateRoomOperator)
    bpy.utils.unregister_class(vrtistOperators.VRtistRoomListUpdateOperator)
    bpy.utils.unregister_class(vrtistOperators.VRtistJoinRoomOperator)
    bpy.utils.unregister_class(vrtistOperators.VRtistRoomItem)
    bpy.utils.unregister_class(vrtistOperators.VRtistProperties)
    bpy.utils.unregister_class(vrtistOperators.VRtistOperator)
    bpy.utils.unregister_class(vrtistOperators.ROOM_UL_ItemRenderer)

    cleanup()
    atexit.unregister(cleanup)
    
if __name__ == "__main__":
    register()
    