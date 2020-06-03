import unittest

from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.proxy import BpyBlendProxy
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import default_context


def sort_pred(x):
    return x[0]


class TestDiff(unittest.TestCase):
    def setUp(self):
        for w in D.worlds:
            D.worlds.remove(w)
        self.proxy = BpyBlendProxy()

    def test_create(self):
        # test_diff.TestDiff.test_create
        self.proxy.load(default_context)
        new_worlds = ["W0", "W1"]
        new_worlds.sort()
        for w in new_worlds:
            D.worlds.new(w)
        diff = BpyBlendDiff()
        diff.diff(self.proxy, default_context)
        for name, delta in diff.collection_deltas:
            self.assertEqual(0, len(delta.items_removed), f"removed count mismatch for {name}")
            self.assertEqual(0, len(delta.items_renamed), f"renamed count mismatch for {name}")
            if name == "worlds":
                self.assertEqual(len(new_worlds), len(delta.items_added), f"added count mismatch for {name}")
                found = list(delta.items_added.keys())
                found.sort()
                self.assertEqual(new_worlds, found, f"added count mismatch for {name}")
            else:
                self.assertEqual(0, len(delta.items_added), f"added count mismatch for {name}")

    def test_remove(self):
        # test_diff.TestDiff.test_create
        new_worlds = ["W0", "W1", "W2"]
        new_worlds.sort()
        for w in new_worlds:
            D.worlds.new(w)

        self.proxy.load(default_context)

        removed = ["W0", "W1"]
        removed.sort()
        for w in removed:
            D.worlds.remove(D.worlds[w])

        diff = BpyBlendDiff()
        diff.diff(self.proxy, default_context)
        for name, delta in diff.collection_deltas:
            self.assertEqual(0, len(delta.items_added), f"added count mismatch for {name}")
            self.assertEqual(0, len(delta.items_renamed), f"renamed count mismatch for {name}")
            if name == "worlds":
                self.assertEqual(len(removed), len(delta.items_removed), f"removed count mismatch for {name}")
                found = [name for name, _ in delta.items_removed]
                found.sort()
                self.assertEqual(removed, found, f"removed count mismatch for {name}")
            else:
                self.assertEqual(0, len(delta.items_added), f"added count mismatch for {name}")

    def test_rename(self):
        # test_diff.TestDiff.test_create
        new_worlds = ["W0", "W1", "W2"]
        new_worlds.sort()
        for w in new_worlds:
            D.worlds.new(w)

        self.proxy.load(default_context)

        renamed = [("W0", "W00"), ("W2", "W22")]
        renamed.sort(key=sort_pred)
        for old_name, new_name in renamed:
            D.worlds[old_name].name = new_name

        diff = BpyBlendDiff()
        diff.diff(self.proxy, default_context)
        for name, delta in diff.collection_deltas:
            self.assertEqual(0, len(delta.items_added), f"added count mismatch for {name}")
            self.assertEqual(0, len(delta.items_removed), f"removed count mismatch for {name}")
            if name == "worlds":
                self.assertEqual(len(renamed), len(delta.items_renamed), f"renamed count mismatch for {name}")
                found = list(delta.items_renamed)
                found.sort(key=sort_pred)
                self.assertEqual(renamed, found, f"removed count mismatch for {name}")
            else:
                self.assertEqual(0, len(delta.items_added), f"added count mismatch for {name}")

    def test_create_delete_rename(self):
        # test_diff.TestDiff.test_create
        new_worlds = ["W0", "W1", "W2", "W4"]
        new_worlds.sort()
        for w in new_worlds:
            D.worlds.new(w)

        self.proxy.load(default_context)

        renamed = [("W0", "W00"), ("W2", "W22"), ("W4", "W44")]
        renamed.sort(key=sort_pred)
        for old_name, new_name in renamed:
            D.worlds[old_name].name = new_name

        added = ["W0", "W5"]
        added.sort()
        for w in added:
            D.worlds.new(w)

        removed = ["W1", "W00"]
        removed.sort()
        for w in removed:
            D.worlds.remove(D.worlds[w])

        diff = BpyBlendDiff()
        diff.diff(self.proxy, default_context)
        for name, delta in diff.collection_deltas:
            if name == "worlds":
                items_added = list(delta.items_added.keys())
                items_added.sort()
                self.assertEqual(items_added, ["W0", "W5"], f"added count mismatch for {name}")
                items_renamed = delta.items_renamed
                items_renamed.sort(key=sort_pred)
                self.assertEqual(items_renamed, [("W2", "W22"), ("W4", "W44")], f"renamed count mismatch for {name}")
                items_removed = [name for name, _ in delta.items_removed]
                items_removed.sort()
                self.assertEqual(items_removed, ["W0", "W1"], f"removed count mismatch for {name}")
            else:
                self.assertEqual(0, len(delta.items_renamed), f"renamed count mismatch for {name}")
                self.assertEqual(0, len(delta.items_removed), f"removed count mismatch for {name}")
                self.assertEqual(0, len(delta.items_added), f"added count mismatch for {name}")
