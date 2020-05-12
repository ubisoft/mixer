from dccsync.share_data import share_data
import bpy


def get_or_create_path(path, data=None) -> bpy.types.Object:
    index = path.rfind("/")
    if index != -1:
        share_data.pending_parenting.add(path)  # Parenting is resolved after consumption of all messages

    # Create or get object
    elem = path[index + 1 :]
    ob = share_data.blender_objects.get(elem)
    if not ob:
        ob = bpy.data.objects.new(elem, data)
        share_data._blender_objects[ob.name_full] = ob
    return ob


def get_or_create_object_data(path, data):
    return get_or_create_path(path, data)


def get_object_path(obj):
    path = obj.name_full
    while obj.parent:
        obj = obj.parent
        if obj:
            path = obj.name_full + "/" + path
    return path
