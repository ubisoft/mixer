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


class TestDirect(TestCase):
    _create_link = f"""
import bpy
lib_file = r"{TestCase._lib_file}"
with bpy.data.libraries.load(lib_file, link=True) as (data_from, data_to):
    data_to.objects = ["Empty", "Camera"]

bpy.data.scenes[0].collection.objects.link(bpy.data.objects["Empty"])
bpy.data.scenes[0].collection.objects.link(bpy.data.objects["Camera"])
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

    def test_reference_direct_datablock(self):
        self.send_string(self._create_link, to=0)

        ref_camera = """
import bpy
bpy.data.scenes[0].camera = bpy.data.objects[0]
"""
        self.send_string(ref_camera, to=0)
        self.assert_matches()

    @unittest.skip("Waiting for BlenddataLibraries.remove in 2.91")
    def test_remove_link_and_library(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.send_string(self._remove_library, to=0)
        self.assert_matches()


class TestIndirect_1(TestCase):
    # Loading the the "Camera" object causes loading of "Camera" camera as "indirect"
    _create_link = f"""
import bpy
lib_file = r"{TestCase._lib_file}"
with bpy.data.libraries.load(lib_file, link=True) as (data_from, data_to):
    data_to.cameras = ["Camera"]
    data_to.objects = ["Camera"]

bpy.data.scenes[0].collection.objects.link(bpy.data.objects["Camera"])
"""

    def test_create_link(self):
        self.send_string(self._create_link, to=0)
        self.assert_matches()

    def test_remove_data_datablock(self):
        self.send_string(self._create_link, to=0)

        # Remove the camera datablock. This is not allowed from the UI but works in a script
        remove_camera_data = """
import bpy
bpy.data.cameras.remove(bpy.data.cameras["Camera"])
"""
        self.send_string(remove_camera_data, to=0)
        self.assert_matches()


class TestIndirect_2(TestCase):
    # Loading the the "Collection" collection causes loading of "Camera" object as "indirect"
    _create_link = f"""
import bpy
lib_file = r"{TestCase._lib_file}"
with bpy.data.libraries.load(lib_file, link=True) as (data_from, data_to):
    data_to.collections = ["Collection"]

bpy.data.scenes[0].collection.children.link(data_to.collections[0])

"""

    def test_create_link(self):
        self.send_string(self._create_link, to=0)
        self.assert_matches()

    def test_remove_object(self):
        self.send_string(self._create_link, to=0)

        # Remove the camera datablock. This is not allowed from the UI but works in a script
        remove_object = """
import bpy
bpy.data.objects.remove(bpy.data.objects["Camera"])
"""
        self.send_string(remove_object, to=0)
        self.assert_matches()

    def test_remove_object_data(self):
        self.send_string(self._create_link, to=0)

        # Remove the camera datablock. This is not allowed from the UI but works in a script
        remove_object_data = """
import bpy
bpy.data.cameras.remove(bpy.data.cameras["Camera"])
"""
        self.send_string(remove_object_data, to=0)
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

    @unittest.skip("Waiting for BlenddataLibraries.remove in 2.91")
    def test_remove_link_and_library(self):
        self.send_string(self._create_link, to=0)
        self.send_string(self._remove_link, to=0)
        self.send_string(self._remove_library, to=0)
        self.assert_matches()


if __name__ == "main":
    unittest.main()
