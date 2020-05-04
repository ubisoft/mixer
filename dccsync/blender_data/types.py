from typing import Any, List

import bpy.types as T  # noqa N812


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
