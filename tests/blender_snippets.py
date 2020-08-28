from typing import Any, List, Optional


def active_layer_collection(
    collection: str, scene: Optional[str] = "Scene", viewlayer: Optional[str] = "View Layer"
) -> str:
    return f"""
import bpy
viewlayer = bpy.data.scenes["{scene}"].view_layers["{viewlayer}"]
collection = viewlayer.layer_collection.children["{collection}"]
viewlayer.active_layer_collection = collection
"""


def active_layer_master_collection(scene: Optional[str] = "Scene", viewlayer: Optional[str] = "View Layer") -> str:
    """
    Select master collection
    """
    return f"""
import bpy
viewlayer = bpy.data.scenes["{scene}"].view_layers["{viewlayer}"]
viewlayer.active_layer_collection = viewlayer.layer_collection
"""


def data_objects_remove(name: str) -> str:
    return f"""
import bpy
object = bpy.data.objects["{name}"]
bpy.data.objects.remove(object)
"""


def data_new(collection_name: str, *args: List[Any]) -> str:
    def string(x: Any):
        if isinstance(x, str):
            return f"'{x}'"
        else:
            return str(x)

    s = ",".join([string(x) for x in args])
    return f"""
import bpy
data = bpy.data.{collection_name}.new({s})
"""


def data_collections_new(name: str) -> str:
    return data_new("collections", name)


def data_collections_remove(collection_name: str) -> List[str]:
    return f"""
import bpy
collection = bpy.data.collections["{collection_name}"]
bpy.data.collections.remove(collection)
"""


def data_collections_rename(old_name: str, new_name: str) -> str:
    return data_rename("collections", old_name, new_name)


def data_lights_update(name: str, property_update: str) -> str:
    return data_update("objects", name, property_update)


def data_lights_rename(old_name: str, new_name: str) -> str:
    return data_rename("lights", old_name, new_name)


def data_objects_new(*args: List[Any]) -> str:
    return data_new("objects", *args)


def data_objects_rename(old_name: str, new_name: str) -> str:
    return data_rename("objects", old_name, new_name)


def data_objects_update(name: str, property_update: str) -> str:
    return data_update("objects", name, property_update)


def data_scenes_rename(old_name: str, new_name: str) -> str:
    return data_rename("scenes", old_name, new_name)


def data_rename(collection_name: str, old_name: str, new_name: str) -> str:
    return f"""
import bpy
bpy.data.{collection_name}["{old_name}"].name = "{new_name}"
"""


def data_update(collection_name: str, name: str, property_update: str) -> str:
    return f"""
import bpy
bpy.data.{collection_name}["{name}"]{property_update}
"""


def ops_objects_light_add(light_type: Optional[str] = "POINT", location: Optional[str] = "0.0, 0.0, 0.0") -> str:
    return f"""
import bpy
bpy.ops.object.light_add(type="{light_type}", location=({location}))
"""


def scene_collection_objects_unilink(object_name: str, scene_name: Optional[str] = "Scene") -> str:
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
object = bpy.data.objects["{object_name}"]
scene.collection.objects.unlink(object)
"""


def scene_collection_children_link(collection_name: str, scene_name: Optional[str] = "Scene") -> str:
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
collection = bpy.data.collections["{collection_name}"]
scene.collection.children.link(collection)
"""


def scene_collection_children_unlink(collection_name: str, scene_name: Optional[str] = "Scene") -> str:
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
collection = bpy.data.collections["{collection_name}"]
scene.collection.children.unlink(collection)
"""


def trigger_scene_update(scene_name: str = "Scene") -> str:
    # Changing anything will trigger an update
    return f"""
import bpy
scene = bpy.data.scenes["{scene_name}"]
uuid = scene.mixer_uuid
scene.mixer_uuid = uuid
"""


def collection_objects_unlink(object_name: str, collection_name: str) -> str:
    return f"""
import bpy
object = bpy.data.objects["{object_name}"]
collection = bpy.data.collections["{collection_name}"]
collection.objects.unlink(object)
"""
