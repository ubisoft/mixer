from dccsync.blender_client.misc import get_or_create_object_data, get_object_path
from dccsync.broadcaster import common
from dccsync.broadcaster.client import Client
from dccsync.share_data import share_data
import bpy


def get_camera_buffer(obj):
    cam = obj.data
    focal = cam.lens
    front_clip_plane = cam.clip_start
    far_clip_plane = cam.clip_end
    aperture = cam.dof.aperture_fstop
    sensor_fit_name = cam.sensor_fit
    sensor_fit = common.SensorFitMode.AUTO
    if sensor_fit_name == "AUTO":
        sensor_fit = common.SensorFitMode.AUTO
    elif sensor_fit_name == "HORIZONTAL":
        sensor_fit = common.SensorFitMode.HORIZONTAL
    elif sensor_fit_name == "VERTICAL":
        sensor_fit = common.SensorFitMode.VERTICAL
    sensor_width = cam.sensor_width
    sensor_height = cam.sensor_height

    path = get_object_path(obj)
    return (
        common.encode_string(path)
        + common.encode_float(focal)
        + common.encode_float(front_clip_plane)
        + common.encode_float(far_clip_plane)
        + common.encode_float(aperture)
        + common.encode_int(sensor_fit.value)
        + common.encode_float(sensor_width)
        + common.encode_float(sensor_height)
    )


def send_camera(client: Client, obj):
    camera_buffer = get_camera_buffer(obj)
    if camera_buffer:
        client.add_command(common.Command(common.MessageType.CAMERA, camera_buffer, 0))
    client.send_camera_animations(obj)


def build_camera(data):
    camera_path, start = common.decode_string(data, 0)

    camera_name = camera_path.split("/")[-1]
    camera = get_or_create_camera(camera_name)

    camera.lens, start = common.decode_float(data, start)
    camera.clip_start, start = common.decode_float(data, start)
    camera.clip_end, start = common.decode_float(data, start)
    camera.dof.aperture_fstop, start = common.decode_float(data, start)
    sensor_fit, start = common.decode_int(data, start)
    camera.sensor_width, start = common.decode_float(data, start)
    camera.sensor_height, start = common.decode_float(data, start)

    if sensor_fit == 0:
        camera.sensor_fit = "AUTO"
    elif sensor_fit == 1:
        camera.sensor_fit = "VERTICAL"
    else:
        camera.sensor_fit = "HORIZONTAL"

    get_or_create_object_data(camera_path, camera)


def get_or_create_camera(camera_name):
    camera = share_data.blender_cameras.get(camera_name)
    if camera:
        return camera
    camera = bpy.data.cameras.new(camera_name)
    share_data._blender_cameras[camera.name_full] = camera
    return camera
