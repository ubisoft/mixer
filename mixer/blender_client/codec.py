"""
Define and register encodable/decodable message types
"""
from mixer import codec
from mixer.broadcaster.common import MessageType
from mixer.blender_client import messages

message_types = {
    MessageType.TRANSFORM: messages.TransformMessage,
}


def register():
    codec.register_message_types(message_types)


def unregister():
    codec.unregister_message_types(message_types)
