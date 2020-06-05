import logging
import traceback
from typing import List, Tuple

from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.json_codec import Codec
from mixer.blender_data.proxy import BpyIDProxy
from mixer.broadcaster import common
from mixer.share_data import share_data

logger = logging.getLogger(__name__)

# No explicit creations here.
# The creations are perfomed as part of an update of an item that does not exist.
# It is easier to manage ctor parameters beyond name that are sometimes required
# and stored the serialized proxy (_ctor_args)


def build_data_remove(buffer):
    if not share_data.use_experimental_sync():
        return

    collection_name, index = common.decode_string(buffer, 0)
    key, index = common.decode_string(buffer, index)
    logger.info("build_data_remove: %s[%s]", collection_name, key)
    BlendData.instance().collection(collection_name).remove(key)


#
# WARNING There ara duplicate keys in blendata collections with linked blendfiles
#
def build_data_update(buffer):
    if not share_data.use_experimental_sync():
        return

    buffer, _ = common.decode_string(buffer, 0)
    codec = Codec()
    try:
        id_proxy = codec.decode(buffer)
        blenddata_path = id_proxy._blenddata_path
        if blenddata_path[0] is None or blenddata_path[1] is None:
            logger.error("build_data_update: invalide blenddata_path : %s", blenddata_path)
            return

        logger.info("build_data_update: %s[%s]", *id_proxy._blenddata_path)
        id_proxy.save()
    except Exception:
        logger.error(
            "Exception during build_data_update\n"
            + traceback.format_exc()
            + "During processing of\n"
            + buffer[0:200]
            + "\n...\n"
            + buffer[-200:0]
        )


def send_data_removals(removals: List[Tuple[str, str]]):
    if not share_data.use_experimental_sync():
        return

    for collection_name, key in removals:
        logger.info("send_removal: %s[%s]", collection_name, key)
        buffer = common.encode_string(collection_name) + common.encode_string(key)
        command = common.Command(common.MessageType.BLENDER_DATA_REMOVE, buffer, 0)
        share_data.client.add_command(command)


def send_data_updates(updates: List[BpyIDProxy]):
    if not share_data.use_experimental_sync():
        return
    if not updates:
        return
    codec = Codec()
    for proxy in updates:
        logger.info("send_data_update %s[%s]", *proxy._blenddata_path)

        encoded_proxy = codec.encode(proxy)
        # For BpyIdProxy, the target is encoded in the proxy._blenddata_path
        buffer = common.encode_string(encoded_proxy)
        command = common.Command(common.MessageType.BLENDER_DATA_UPDATE, buffer, 0)
        share_data.client.add_command(command)
