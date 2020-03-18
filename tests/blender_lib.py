"""
Functions to be remotely executed in Blender via python_server.py

Remote execution relies on source code extractiona and transmission to the
execution sever, so each function must contain its imports
"""


def save(path: str):
    import bpy
    bpy.ops.wm.save_as_mainfile(filepath=path)


def quit():
    import bpy
    bpy.ops.wm.quit_blender()


def rename_mesh(old_name: str, new_name: str):
    import bpy
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.name == old_name:
            obj.name = new_name


def add(radius=1.0, type='EMPTY', location=(0.0, 0.0, 0.0)):
    import bpy
    bpy.ops.object.add(radius=radius, type=type, location=location)
