"""
Type related utilities
"""
import functools
from typing import Any, List, Type

import bpy.types as T  # noqa N812
import mathutils

builtin_types = {type(None), float, int, bool, str, set, bytes}
vector_types = {mathutils.Vector, mathutils.Color, mathutils.Quaternion, mathutils.Euler}


def is_builtin(type_: Type):
    return type_ in builtin_types


def is_vector(type_: Type):
    return type_ in vector_types


def is_matrix(type_: Type):
    return type_ is mathutils.Matrix


def is_pointer(property_) -> bool:
    return property_.bl_rna is T.PointerProperty.bl_rna


def bases_of(rna_property: T.Property) -> List[Any]:
    """
    Including the current type and None as root
    """
    bases = []
    base = rna_property
    while base is not None:
        bases.append(base)
        base = None if base.base is None else base.base.bl_rna
    return bases


def is_instance(rna_property: T.Property, base: T.Property) -> bool:
    return base in bases_of(rna_property)


def is_pointer_to(rna_property: T.Property, base: type) -> bool:
    return is_pointer(rna_property) and is_instance(rna_property.fixed_type, base.bl_rna)


@functools.lru_cache(maxsize=None)
def sub_id_type(type_):
    """Returns the base closest to ID (e.g Light for PointLight)"""
    sub_id_list = [t for t in type_.mro() if issubclass(t, T.ID) and t != T.ID]
    if sub_id_list:
        return sub_id_list[-1]
    return None
