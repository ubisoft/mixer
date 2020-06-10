import logging
import traceback
from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.filter import safe_context
from mixer.blender_data.json_codec import Codec
from mixer.blender_data.proxy import BlendDataVisitContext
from mixer.broadcaster import common
from mixer.share_data import share_data

import bpy.types

logger = logging.getLogger(__name__)


#
# WARNING There ara duplicate keys in blendata collections with linked blendfiles
#
def build_data_update(buffer):
    if not share_data.use_experimental_sync():
        return

    blenddata_collection_name, index = common.decode_string(buffer, 0)
    key, index = common.decode_string(buffer, index)
    data, _ = common.decode_string(buffer, index)
    logger.info("build_data_update %s[%s]", blenddata_collection_name, key)
    codec = Codec()
    blenddata = BlendData.instance()
    collection = blenddata.bpy_collection(blenddata_collection_name)
    # TODO will fail when name != name_full
    try:
        id_proxy = codec.decode(data)
        id_proxy.save(collection, key)
    except Exception:
        logger.error("Build_data-update: Exception :")
        logger.error("\n" + traceback.format_exc())
        logger.error("while processing message:")
        logger.error("\n" + data)


def send_update(updated_id: bpy.types.ID):
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
    id_proxy.load(updated_id, safe_context, BlendDataVisitContext(safe_context))
    codec = Codec()
    try:
        message = codec.encode(id_proxy)
    except Exception:
        logger.error("send_update: Exception :")
        logger.error("\n" + traceback.format_exc())
        logger.error(f"while processing bpy.data.{collection_name}[{key}]:")

    buffer = common.encode_string(collection_name) + common.encode_string(key) + common.encode_string(message)
    command = common.Command(common.MessageType.BLENDER_DATA_UPDATE, buffer, 0)
    share_data.client.add_command(command)
