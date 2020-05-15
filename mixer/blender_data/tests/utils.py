import functools
from pathlib import Path
import sys
from typing import Iterable, List, Union
import unittest

from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.types import is_builtin, is_vector, is_matrix
from mixer.blender_data.filter import default_context


this_folder = Path(__file__).parent
test_blend_file = str(this_folder / "test_data.blend")


def matches_type(p, t):
    # sic ...
    if p.bl_rna is T.CollectionProperty.bl_rna and p.srna and p.srna.bl_rna is t.bl_rna:
        return True


def register_bl_equals(testcase, context):
    equals = functools.partial(bl_equals, context=context, skip_name=True)
    for type_name in dir(T):
        type_ = getattr(T, type_name)
        testcase.addTypeEqualityFunc(type_, equals)


def clone(src):
    dst = src.__class__()
    for k, v in dir(src):
        setattr(dst, k, v)
    return dst


def equals(attr_a, attr_b, context=default_context):
    type_a = type(attr_a)
    type_b = type(attr_b)
    if type_a != type_b:
        return False

    if is_builtin(type_a) or is_vector(type_a) or is_matrix(type_a):
        if attr_a != attr_b:
            return False
    elif type_a == T.bpy_prop_array:
        if attr_a != attr_b:
            return False
    elif issubclass(type_a, T.bpy_prop_collection):
        for key in attr_a.keys():
            attr_a_i = attr_a[key]
            attr_b_i = attr_b[key]
            if not equals(attr_a_i, attr_b_i):
                return False
    elif issubclass(type_a, T.bpy_struct):
        for name, _ in context.properties(attr_a.bl_rna):
            attr_a_i = getattr(attr_a, name)
            attr_b_i = getattr(attr_b, name)
            if not equals(attr_a_i, attr_b_i):
                return False
    else:
        raise NotImplementedError

    return True


# context = default_context


def bl_equals(attr_a, attr_b, msg=None, skip_name=False, context=None):
    """
    skip_name for the top level name only since cloned objects have different names
    """
    failureException = unittest.TestCase.failureException
    type_a = type(attr_a)
    type_b = type(attr_b)
    if type_a != type_b:
        raise failureException(f"Different types : {type_a} and {type_b}")
    if is_builtin(type_a) or is_vector(type_a) or is_matrix(type_a):
        if attr_a != attr_b:
            raise failureException(f"Different values : {attr_a} and {attr_b}")
    elif type_a == T.bpy_prop_array:
        if attr_a != attr_b:
            raise failureException(f"Different values for array : {attr_a} and {attr_b}")
    elif issubclass(type_a, T.bpy_prop_collection):
        for key in attr_a.keys():
            attr_a_i = attr_a[key]
            attr_b_i = attr_b[key]
            if not bl_equals(attr_a_i, attr_b_i, msg, skip_name=False, context=context):
                raise failureException(
                    f"Different values for collection items at key {key} : {attr_a_i} and {attr_b_i}"
                )
    elif issubclass(type_a, T.bpy_struct):
        for name, _ in context.properties(attr_a.bl_rna):
            if skip_name and name == "name":
                return True
            attr_a_i = getattr(attr_a, name)
            attr_b_i = getattr(attr_b, name)
            if not bl_equals(attr_a_i, attr_b_i, msg, skip_name=False, context=context):
                raise failureException(
                    f"Different values for collection items at key {name} : {attr_a_i} and {attr_b_i}"
                )
    else:
        raise NotImplementedError

    return True


def run_tests(test_names: Union[str, List[str]] = None):
    if test_names is not None:
        test_names = test_names if isinstance(test_names, Iterable) else [test_names]
        suite = unittest.defaultTestLoader.loadTestsFromNames(test_names)
    else:
        this_dir = str(Path(__file__).parent)
        suite = unittest.defaultTestLoader.discover(this_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


def main():
    module = sys.modules[__name__]
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


def main_ci():
    module = sys.modules[__name__]
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Tests failed")


if __name__ == "__main__":
    main_ci()
