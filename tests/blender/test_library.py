import unittest

from tests import files_folder
from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class TestCase(BlenderTestCase):
    _lib_file = str(files_folder() / "lib_1.blend")

    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)


class TestEmptyDirect(TestCase):
    _create_link = f"""
import bpy
lib_file = r"{TestCase._lib_file}"
with bpy.data.libraries.load(lib_file, link=True) as (data_from, data_to):
    data_to.objects = ["Empty"]

empty = bpy.data.objects["Empty"]
bpy.data.scenes[0].collection.objects.link(empty)
"""

    _remove_link = """
import bpy
bpy.data.objects.remove(bpy.data.objects["Empty"])
"""

    _remove_library = """
import bpy
bpy.data.libraries.remove(bpy.data.library[0])
"""

    def test_create_link(self):
        self.send_string(self._create_link, to=0)
        self.assert_matches()

    def test_remove_link(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.assert_matches()

    @unittest.skip("Waiting for BlenddataLibraries.remove in 2.91")
    def test_remove_link_and_library(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.send_string(self._remove_library, to=0)
        self.assert_matches()


class TestCameraIndirect(TestCase):
    # Loading the the "Camera" objects causes loading of "Camera" camera as "indirect"
    _create_link = f"""
import bpy
lib_file = r"{TestCase._lib_file}"
with bpy.data.libraries.load(lib_file, link=True) as (data_from, data_to):
    data_to.objects = ["Camera"]

for item in data_to.objects:
    bpy.data.scenes[0].collection.objects.link(item)

"""

    _remove_link = """
import bpy
bpy.data.objects.remove(bpy.data.objects["Camera"])
"""

    def test_create_link(self):
        self.send_string(self._create_link, to=0)
        self.assert_matches()

    def test_remove_link(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.assert_matches()


class TestLinkAll(TestCase):
    _create_link = f"""
import bpy
lib_file = r"{TestCase._lib_file}"
with bpy.data.libraries.load(lib_file, link=True) as (data_from, data_to):
    data_to.objects = data_from.objects
    data_to.collections = data_from.collections

for item in data_to.objects:
    bpy.data.scenes[0].collection.objects.link(item)

for item in data_to.collections:
    bpy.data.scenes[0].collection.children.link(item)

"""

    _remove_link = """
import bpy
bpy.data.objects.remove(bpy.data.objects["Empty"])
"""

    _remove_library = """
import bpy
bpy.data.libraries.remove(bpy.data.library[0])
"""

    def test_create_link(self):
        self.send_string(self._create_link, to=0)
        self.assert_matches()

    def test_remove_link(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.assert_matches()

    @unittest.skip("Waiting for BlenddataLibraries.remove in 2.91")
    def test_remove_link_and_library(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.send_string(self._remove_library, to=0)
        self.assert_matches()


if __name__ == "main":
    unittest.main()
