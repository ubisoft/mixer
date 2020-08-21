"""
Definition of messages

Currently used only in tests. Could be used also in all send_xxx() and build_xxx() functions
"""
from dataclasses import dataclass

from mixer.codec import Message, Matrix


@dataclass(order=True)
class TransformMessage(Message):
    path: str
    m1: Matrix
    m2: Matrix
    m3: Matrix
