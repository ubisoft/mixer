import logging

from dccsync.broadcaster import common
from dccsync.broadcaster.client import Client
from dccsync.share_data import share_data


logger = logging.getLogger(__name__)


# see send_collection on what to encode next
def send_data(client: Client, collection_name: str, data_name: str):
    logger.debug("send_data %s %s", collection_name, data_name)
    buffer = None
    command = common.Command(common.MessageType.DATA_ADDED, buffer, 0)
    client.add_command(command)


def build_data(buffer):
    data_name, _ = common.decode_string(buffer, 0)
    collection_name = None
    logger.debug("build_data %s", collection_name, data_name)
    share_data.blender_datas.collection(collection_name).new(data_name)


def send_data_removed(client: Client, collection_name: str, data_name: str):
    logger.debug("send_data %s %s", collection_name, data_name)
    buffer = common.encode_string(collection_name) + common.encode_string(data_name)
    client.add_command(common.Command(common.MessageType.DATA_REMOVED, buffer, 0))


def build_data_removed(data):
    data_name, _ = common.decode_string(data, 0)
    collection_name, _ = common.decode_string(data, 0)
    logger.debug("build_data_removed %s %s", collection_name, data_name)
    share_data.blender_datas.getattr(collection_name).remove(data_name)


def send_data_renamed(client: Client, collection_name: str, old_name: str, new_name: str):
    logger.debug("send_data_renamed %s to %s", old_name, new_name)
    buffer = common.encode_string(collection_name + common.encode_string(old_name) + common.encode_string(new_name))
    client.add_command(common.Command(common.MessageType.DATA_RENAMED, buffer, 0))


def build_data_renamed(data):
    # decode collection name, old name, new name
    collection_name, index = common.decode_string(data, 0)
    old_name, index = common.decode_string(data, index)
    new_name, _ = common.decode_string(data, index)
    logger.debug("build_data_renamed in %s : %s to %s", collection_name, old_name, new_name)
    share_data.blender_datas.getattr(collection_name).rename(old_name, new_name)
