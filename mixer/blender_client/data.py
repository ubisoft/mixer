import logging
import traceback
from typing import List, Tuple

from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.filter import safe_context
from mixer.blender_data.json_codec import Codec
from mixer.broadcaster import common
from mixer.share_data import share_data

import bpy.types
from mixer.blender_data.proxy import VisitState

logger = logging.getLogger(__name__)


def build_data_new(buffer):
    if not share_data.use_experimental_sync():
        return

    collection_name, index = common.decode_string(buffer, 0)
    key, index = common.decode_string(buffer, index)
    logger.info("build_data_new: %s[%s]", collection_name, key)
    # TODO some ctors have more more parameters than key,
    # e.g BlendDataObjects: use None, then rely on the update ? The sender must send None as additional ctor param
    # when a metaball is created a metaball and an object are created and the object creation requires the metaball ID
    # as its data
    BlendData.instance().collection(collection_name).ctor(key)


#
# WARNING There ara duplicate keys in blendata collections with linked blendfiles
#
def build_data_update(buffer):
    if not share_data.use_experimental_sync():
        return

    collection_name, index = common.decode_string(buffer, 0)
    key, index = common.decode_string(buffer, index)
    buffer, _ = common.decode_string(buffer, index)
    logger.info("build_data_update: %s[%s]", collection_name, key)
    codec = Codec()
    try:
        id_proxy = codec.decode(buffer)
        blenddata = BlendData.instance()
        collection = blenddata.bpy_collection(collection_name)
        # TODO will fail when name != name_full
        id_proxy.save(collection, key)
    except Exception:
        logging.error(
            "Exception during build_data_update\n" + traceback.format_exc() + "During processing of\n" + buffer
        )


def send_data_new(collection, key: str):
    if not share_data.use_experimental_sync():
        return

    # TODO better and faster
    collection_name = BlendData.instance().bl_collection_name_from_ID(collection[key])
    logger.info("send_added: %s[%s]", collection_name, key)
    buffer = common.encode_string(collection_name) + common.encode_string(key)
    command = common.Command(common.MessageType.BLENDER_DATA_NEW, buffer, 0)
    share_data.client.add_command(command)


def send_data_update(updated_id: bpy.types.ID):
    # Temporary for the initial test with light and camera.
    # loads a full proxy from the depgraph updated ID
    if not share_data.use_experimental_sync():
        return

    logger.info("send_data_update %s", updated_id)

    global_proxy = share_data.proxy
    blenddata = BlendData.instance()
    collection_name = blenddata.bl_collection_name_from_ID(updated_id)
    if updated_id.name != updated_id.name_full:
        logging.warning("Not implemented linked objects : {updated_id.name} {updated_id.name_full}")
    key = updated_id.name
    id_proxy = global_proxy.find(collection_name, key)
    if id_proxy is None:
        return

    id_proxy.load(updated_id, VisitState(global_proxy.root_ids, safe_context))
    codec = Codec()
    message = codec.encode(id_proxy)
    buffer = common.encode_string(collection_name) + common.encode_string(key) + common.encode_string(message)
    command = common.Command(common.MessageType.BLENDER_DATA_UPDATE, buffer, 0)
    share_data.client.add_command(command)


def send_data_updates(updates: List[Tuple[str, str]]):
    if not share_data.use_experimental_sync():
        return
    if not updates:
        return
    global_proxy = share_data.proxy
    codec = Codec()
    for collection_name, key in updates:
        id_proxy = global_proxy.find(collection_name, key)
        if id_proxy is None:
            return
        message = codec.encode(id_proxy)
        buffer = common.encode_string(collection_name) + common.encode_string(key) + common.encode_string(message)
        command = common.Command(common.MessageType.BLENDER_DATA_UPDATE, buffer, 0)
        share_data.client.add_command(command)
