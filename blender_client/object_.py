from ..broadcaster import common
from ..broadcaster.client import Client
from ..share_data import share_data
import logging
import bpy

logger = logging.getLogger(__name__)


def send_object_visibility(client: Client, object_: bpy.types.Object):
    logger.debug("send_object_visibility %s", object_.name_full)
    buffer = (
        common.encode_string(object_.name_full)
        + common.encode_bool(object_.hide_viewport)
        + common.encode_bool(object_.hide_select)
        + common.encode_bool(object_.hide_render)
        + common.encode_bool(object_.hide_get())
    )
    client.add_command(common.Command(common.MessageType.OBJECT_VISIBILITY, buffer, 0))


def build_object_visibility(data):
    name_full, index = common.decode_string(data, 0)
    hide_viewport, index = common.decode_bool(data, index)
    hide_select, index = common.decode_bool(data, index)
    hide_render, index = common.decode_bool(data, index)
    hide_get, index = common.decode_bool(data, index)

    logger.debug("build_object_visibility %s", name_full)
    object_ = share_data.blender_objects.get(name_full)
    if object_ is None:
        logger.warning("build_object_visibility %s : object not found", name_full)
        return
    object_.hide_viewport = hide_viewport
    object_.hide_select = hide_select
    object_.hide_render = hide_render
    object_.hide_set(hide_get)
