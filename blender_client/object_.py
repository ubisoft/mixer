from ..broadcaster import common
from ..shareData import shareData
import logging
import bpy

logger = logging.getLogger(__name__)


def sendObjectVisibility(client: 'ClientBlender', object_: bpy.types.Object):
    logger.debug("sendObjectVisibility %s", object_.name_full)
    buffer = common.encodeString(object_.name_full) + \
        common.encodeBool(object_.hide_viewport) + \
        common.encodeBool(object_.hide_select) + \
        common.encodeBool(object_.hide_render) + \
        common.encodeBool(object_.hide_get())
    client.addCommand(common.Command(
        common.MessageType.OBJECT_VISIBILITY, buffer, 0))


def buildObjectVisibility(data):
    name_full, index = common.decodeString(data, 0)
    hide_viewport, index = common.decodeBool(data, index)
    hide_select, index = common.decodeBool(data, index)
    hide_render, index = common.decodeBool(data, index)
    hide_get, index = common.decodeBool(data, index)

    logger.debug("buildObjectVisibility %s", name_full)
    object_ = shareData.blenderObjects.get(name_full)
    if object_ is None:
        logger.warning("buildObjectVisibility %s : object not found", name_full)
        return
    object_.hide_viewport = hide_viewport
    object_.hide_select = hide_select
    object_.hide_render = hide_render
    object_.hide_set(hide_get)
