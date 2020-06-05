"""Type specific helpers for Proxy load and save
"""
from typing import Any, ItemsView, List, TypeVar
import bpy.types as T  # noqa N812

BpyIDProxy = TypeVar("BpyIDProxy")


def ctor_args(id_: T.ID, proxy: BpyIDProxy) -> List[Any]:
    """Builds a list of arguments required to create an item in a bpy.data collection

    For instance, bpy.data.objects.new() requires a string (the name) and a bpy.types.ID that
    will be linked to its data attribute. The list only include arguments after the item name,
    that is always required.

    Args:
        id_ : determines the bpy.data collection where the item will be created
        proxy : the Proxy that contains the required argument value

    """

    if isinstance(id_, T.Object):
        # a BpyIDProxy
        return [proxy.data("data")]
    if isinstance(id_, T.Light):
        return [proxy.data("type")]
    return None


def conditional_properties(id_: T.ID, properties: ItemsView) -> ItemsView:
    """Filter properties list according to a specific property value in the same ID

    This prevents loading values that cannot always be saved, such as Object.instance_collection
    that can only be saved when Object.data is None

    Args:
        properties: the properties list to filter
    Returns:

    """
    if isinstance(id_, T.Object):
        if not id_.data:
            # Empty
            return properties
        filtered = {}
        filter_props = ["instance_collection"]
        filtered = {k: v for k, v in properties if k not in filter_props}
        return filtered.items()

    if isinstance(id_, T.MetaBall):
        if not id_.use_auto_texspace:
            return properties
        filter_props = ["texspace_location", "texspace_size"]
        filtered = {k: v for k, v in properties if k not in filter_props}
        return filtered.items()

    return properties
