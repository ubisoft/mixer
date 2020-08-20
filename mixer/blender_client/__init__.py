"""
This package defines how we send Blender updates to the server, and how we interpret updates we receive to update
Blender's data.

These functionalities are implemented in the BlenderClient class and in submodules of the package.

Submodules with a well defined entity name (camera, collection, light, ...) handle updates for the corresponding
data type in Blender. The goal is to replace all this specific code with the submodule data.py, which use
the blender_data package to treat updates of Blender's data in a generic way.

Specific code will still be required to handle non-Blender clients. As an example, mesh.py add to the MESH
message a triangulated, with modifiers applied, of the mesh. This is for non-Blender clients. In the future we want to
move these kind of specific processes to a plug-in system.

"""
