import logging

from mixer.blender_data.blenddata import BlendData
from mixer.blender_data.filter import safe_context
from mixer.blender_data.json_codec import Codec
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

    collection_name, index = common.decode_string(buffer, 0)
    key, index = common.decode_string(buffer, index)
    buffer, _ = common.decode_string(buffer, index)
    logger.debug("build_data_update")
    codec = Codec()
    id_proxy = codec.decode(buffer)
    blenddata = BlendData.instance()
    collection = blenddata.bpy_collection(collection_name)
    # TODO will fail when name != name_full
    id_proxy.save(collection, key)


def send_update(updated_id: bpy.types.ID):
    if not share_data.use_experimental_sync():
        return

    global_proxy = share_data.proxy
    blenddata = BlendData.instance()
    collection_name = blenddata.bl_collection_name_from_ID(updated_id)
    if updated_id.name != updated_id.name_full:
        logging.warning("Not implemented linked objects : {updated_id.name} {updated_id.name_full}")
    key = updated_id.name
    id_proxy = global_proxy.find(collection_name, key)
    if id_proxy is None:
        return
    id_proxy.load(updated_id, safe_context, global_proxy.root_ids)
    codec = Codec()
    message = codec.encode(id_proxy)
    buffer = common.encode_string(collection_name) + common.encode_string(key) + common.encode_string(message)
    command = common.Command(common.MessageType.BLENDER_DATA_UPDATE, buffer, 0)
    share_data.client.add_command(command)
