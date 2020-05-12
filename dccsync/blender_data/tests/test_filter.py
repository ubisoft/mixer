import unittest

from bpy import data as D  # noqa
from bpy import types as T  # noqa
from dccsync.blender_data.tests.utils import matches_type

from dccsync.blender_data.filter import (
    CollectionFilterOut,
    Context,
    FilterStack,
    TypeFilterIn,
    TypeFilterOut,
)


class TestPointerFilterOut(unittest.TestCase):
    def test_exact_class(self):
        filter_stack = FilterStack()
        filter_set = {T.Scene: TypeFilterOut(T.SceneEEVEE)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.SceneEEVEE) for _, p in props]))


class TestTypeFilterIn(unittest.TestCase):
    def test_exact_class(self):
        filter_stack = FilterStack()
        filter_set = {T.BlendData: TypeFilterIn(T.CollectionProperty)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = list(context.properties(T.BlendData))
        self.assertTrue(any([matches_type(p, T.BlendDataCameras) for _, p in props]))
        self.assertFalse(any([matches_type(p, T.StringProperty) for _, p in props]))


class TestCollectionFilterOut(unittest.TestCase):
    def test_exact_class(self):
        filter_stack = FilterStack()
        filter_set = {T.Mesh: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))

    def test_base_class(self):
        filter_stack = FilterStack()
        # Exclude on ID, applies to derived classes
        filter_set = {T.ID: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))

    def test_root_class(self):
        filter_stack = FilterStack()
        # Exclude on all classes
        filter_set = {None: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertFalse(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))

    def test_unrelated_class(self):
        filter_stack = FilterStack()
        # Exclude on unrelated class : does nothing
        filter_set = {T.Collection: CollectionFilterOut(T.MeshVertices)}
        filter_stack.append(filter_set)
        context = Context(filter_stack)
        props = context.properties(T.Mesh)
        self.assertTrue(any([matches_type(p, T.MeshVertices) for _, p in props]))
        self.assertTrue(any([matches_type(p, T.MeshLoops) for _, p in props]))
