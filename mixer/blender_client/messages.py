"""
Definition of messages

Currently used only in tests. Could be used also in all send_xxx() and build_xxx() functions
"""
from dataclasses import dataclass

from mixer.codec import Message, Color, Matrix


@dataclass(order=True)
class TransformMessage(Message):
    path: str
    m1: Matrix
    m2: Matrix
    m3: Matrix


@dataclass(order=True)
class LightMessage(Message):
    path: str
    name: str
    type_: int
    shadow: int
    color: Color
    energy: float
    spot_size: float
    spot_blend: float
