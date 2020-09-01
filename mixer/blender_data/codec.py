"""
Define and register encodable/decodable message types
"""
from mixer import codec
from mixer.broadcaster.common import MessageType
from mixer.blender_data import messages

message_types = {
    MessageType.BLENDER_DATA_CREATE: messages.BlenderCreateMessage,
    MessageType.BLENDER_DATA_UPDATE: messages.BlenderUpdateMessage,
    MessageType.BLENDER_DATA_REMOVE: messages.BlenderRemoveMessage,
    MessageType.BLENDER_DATA_RENAME: messages.BlenderRenameMessage,
}


def register():
    codec.register_message_types(message_types)


def unregister():
    codec.unregister_message_types(message_types)
