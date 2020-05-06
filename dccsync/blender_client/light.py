from dccsync.blender_client.misc import get_or_create_object_data, get_or_create_path, get_object_path
from dccsync.broadcaster import common
from dccsync.broadcaster.client import Client
from dccsync.share_data import share_data
import bpy


def get_light_buffer(obj):
    light = obj.data
    light_type_name = light.type
    light_type = common.LightType.SUN
    if light_type_name == "POINT":
        light_type = common.LightType.POINT
    elif light_type_name == "SPOT":
        light_type = common.LightType.SPOT
    elif light_type_name == "SUN":
        light_type = common.LightType.SUN
    else:
        return None
    color = light.color
    power = light.energy
    if bpy.context.scene.render.engine == "CYCLES":
        shadow = light.cycles.cast_shadow
    else:
        shadow = light.use_shadow

    spot_blend = 10.0
    spot_size = 0.0
    if light_type == common.LightType.SPOT:
        spot_size = light.spot_size
        spot_blend = light.spot_blend

    return (
        common.encode_string(get_object_path(obj))
        + common.encode_int(light_type.value)
        + common.encode_int(shadow)
        + common.encode_color(color)
        + common.encode_float(power)
        + common.encode_float(spot_size)
        + common.encode_float(spot_blend)
    )


def send_light(client: Client, obj):
    light_buffer = get_light_buffer(obj)
    if light_buffer:
        client.add_command(common.Command(common.MessageType.LIGHT, light_buffer, 0))


def build_light(data):
    light_path, start = common.decode_string(data, 0)
    light_type, start = common.decode_int(data, start)
    blighttype = "POINT"
    if light_type == common.LightType.SUN.value:
        blighttype = "SUN"
    elif light_type == common.LightType.POINT.value:
        blighttype = "POINT"
    else:
        blighttype = "SPOT"

    light_name = light_path.split("/")[-1]
    light = get_or_create_light(light_name, blighttype)

    shadow, start = common.decode_int(data, start)
    if shadow != 0:
        light.use_shadow = True
    else:
        light.use_shadow = False

    color, start = common.decode_color(data, start)
    light.color = (color[0], color[1], color[2])
    light.energy, start = common.decode_float(data, start)
    if light_type == common.LightType.SPOT.value:
        light.spot_size, start = common.decode_float(data, start)
        light.spot_blend, start = common.decode_float(data, start)

    get_or_create_object_data(light_path, light)


def get_or_create_light(light_name, light_type):
    light = share_data.blender_lights.get(light_name)
    if light:
        return light
    light = bpy.data.lights.new(light_name, type=light_type)
    share_data._blender_lights[light.name_full] = light
    return light
