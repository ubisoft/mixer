"""
Definition of messages used by the full Blender protocol

Currently used only in tests. Could be used also in all send_xxx() and build_xxx() functions
"""

from dataclasses import dataclass

from mixer.codec import Message


@dataclass(order=True)
class BlenderCreateMessage(Message):
    proxy_string: str


@dataclass(order=True)
class BlenderUpdateMessage(Message):
    proxy_string: str


@dataclass(order=True)
class BlenderRemoveMessage(Message):
    uuid: str
    debug_info: str


@dataclass(order=True)
class BlenderRenameMessage(Message):
    uuid: str
    new_name: str
    debug_info: str
