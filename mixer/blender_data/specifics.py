from typing import TypeVar
import bpy.types as T  # noqa N812

BpyIDProxy = TypeVar("BpyIDProxy")


def ctor_args(id_: T.ID, proxy: BpyIDProxy):
    """
    The ctor args for adding an item in BlendData collection, excluding the name
    """
    if isinstance(id_, T.Object):
        return [proxy.data("data")]
    if isinstance(id_, T.Light):
        return [proxy.data("type")]
    return None
