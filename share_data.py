from datetime import datetime
from typing import List, Mapping, Set
from collections import namedtuple
import bpy

ObjectVisibility = namedtuple("ObjectVisibility", ["hide_viewport", "hide_select", "hide_render", "visible_get"])


def object_visibility(o: bpy.types.Object):
    return ObjectVisibility(o.hide_viewport, o.hide_select, o.hide_render, o.visible_get())


class CollectionInfo:
    def __init__(
        self, hide_viewport: bool, instance_offset, children: List[str], parent: List[str], objects: List[str] = None
    ):
        self.hide_viewport = hide_viewport
        self.instance_offset = instance_offset
        self.children = children
        self.parent = parent
        self.objects = objects or []


class SceneInfo:
    def __init__(self, children: List[str], objects: List[str] = None):
        self.children = children
        self.objects = objects or []


class ShareData:
    def __init__(self):
        self.runId = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_id = 0  # For logging and debug
        self.client = None

        # as received fom LIST_ALL_CLIENTS
        self.client_ids: List[Mapping[str, str]] = None

        self.isLocal = False
        self.localServerProcess = None
        self.selected_objects_names = []
        self.depsgraph = None

        self.current_statistics = None
        self.current_stats_timer = None
        self.auto_save_statistics = False
        self.statistics_directory = None

        self.clear_room_data()

    def clear_room_data(self):
        # equivalent to handlers set
        self.currentRoom: str = None

        self.objectsAdded: Set(str) = set()
        self.objectsRemoved: Set(str) = set()
        self.collections_added: Set(str) = set()
        self.collections_removed: Set(str) = set()
        self.scenes_added: Set(str) = set()
        self.scenes_removed: Set(str) = set()

        # key : collection name
        self.objects_added_to_collection: Mapping(str, str) = {}
        self.objects_removed_from_collection: Mapping(str, str) = {}
        self.collections_added_to_collection: Set(str, str) = set()
        self.collections_removed_from_collection: Set(str, str) = set()

        # key : scene name
        self.objects_added_to_scene: Mapping(str, str) = {}
        self.objects_removed_from_scene: Mapping(str, str) = {}
        self.collections_added_to_scene: Set(str, str) = set()
        self.collections_removed_from_scene: Set(str, str) = set()

        # All non master collections
        self.collections_info: Mapping[str, CollectionInfo] = {}

        # Master collections
        self.scenes_info: Mapping[str, SceneInfo] = {}

        self.objects_reparented = set()
        self.objects_parents = {}
        self.objects_renamed = {}
        self.objectsTransformed = set()
        self.objects_transforms = {}
        self.objects_visibility_changed: Set[str] = set()
        self.objects_visibility: Mapping[str, ObjectVisibility] = {}

        self.old_objects: Mapping[str, bpy.types.Object] = {}

        # {object_path: [collection_name]}
        self.restore_toCollections: Mapping[str, List[str]] = {}

        # {object_path: [collection_name]}
        self.restore_toCollections: Mapping[str, List[str]] = {}

        self._blender_objects = {}
        self.blender_objectsDirty = True

        self._blender_materials = {}
        self.blender_materials_dirty = True

        self._blender_meshes = {}
        self.blender_meshes_dirty = True

        self._blender_grease_pencils = {}
        self.blender_grease_pencils_dirty = True

        self._blender_cameras = {}
        self.blender_camerasDirty = True

        self._blender_lights = {}
        self.blender_lightsDirty = True
        self._blender_collections: Mapping[str, bpy.types.Collection] = {}
        self.blender_collections_dirty = True

        self.pendingParenting = set()

    def leave_current_room(self):
        if self.client is not None:
            self.client.leave_room(share_data.currentRoom)
        self.clear_room_data()

        self._blender_scenes: Mapping[str, bpy.types.Scene] = {}
        self.blender_scenesDirty = True

    def clear_before_state(self):
        # These objects contain the "before" state when entering the update_post handler
        # They must be empty before the first update so that the whole scene is sent
        self.old_objects = {}
        self.collections_info = {}
        self.scenes_info = {}

    def set_dirty(self):
        self.blender_objectsDirty = True
        self.blender_materials_dirty = True
        self.blender_meshes_dirty = True
        self.blender_grease_pencils_dirty = True
        self.blender_camerasDirty = True
        self.blender_lightsDirty = True
        self.blender_collections_dirty = True
        self.blender_scenesDirty = True

    def get_blender_property(self, property, property_dirty, elems):
        if not property_dirty:
            return property
        property = {x.name_full: x for x in elems}
        property_dirty = False
        return property

    @property
    def blender_objects(self):
        if not self.blender_objectsDirty:
            return self._blender_objects
        self._blender_objects = {x.name_full: x for x in bpy.data.objects}
        self.blender_objectsDirty = False
        return self._blender_objects

    @property
    def blender_materials(self):
        if not self.blender_materials_dirty:
            return self._blender_materials
        self._blender_materials = {x.name_full: x for x in bpy.data.materials}
        self.blender_materials_dirty = False
        return self._blender_materials

    @property
    def blender_meshes(self):
        if not self.blender_meshes_dirty:
            return self._blender_meshes
        self._blender_meshes = {x.name_full: x for x in bpy.data.meshes}
        self.blender_meshes_dirty = False
        return self._blender_meshes

    @property
    def blender_grease_pencils(self):
        if not self.blender_grease_pencils_dirty:
            return self._blender_grease_pencils
        self._blender_grease_pencils = {x.name_full: x for x in bpy.data.grease_pencils}
        self.blender_grease_pencils_dirty = False
        return self._blender_grease_pencils

    @property
    def blender_cameras(self):
        if not self.blender_camerasDirty:
            return self._blender_cameras
        self._blender_cameras = {x.name_full: x for x in bpy.data.cameras}
        self.blender_camerasDirty = False
        return self._blender_cameras

    @property
    def blender_lights(self):
        if not self.blender_lightsDirty:
            return self._blender_lights
        self._blender_lights = {x.name_full: x for x in bpy.data.lights}
        self.blender_lightsDirty = False
        return self._blender_lights

    @property
    def blender_collections(self):
        if not self.blender_collections_dirty:
            return self._blender_collections
        self._blender_collections = {x.name_full: x for x in bpy.data.collections}
        self.blender_collections_dirty = False
        return self._blender_collections

    @property
    def blender_scenes(self):
        if not self.blender_scenesDirty:
            return self._blender_scenes
        self._blender_scenes = {x.name_full: x for x in bpy.data.scenes}
        self.blender_scenesDirty = False
        return self._blender_scenes

    def clear_changed_frame_related_lists(self):
        self.objectsTransformed.clear()

    def clear_lists(self):
        """
        Clear the lists that record change between previous and current state
        """
        self.scenes_added.clear()
        self.scenes_removed.clear()

        self.collections_added.clear()
        self.collections_removed.clear()

        self.collections_added_to_collection.clear()
        self.collections_removed_from_collection.clear()
        self.objects_added_to_collection.clear()
        self.objects_removed_from_collection.clear()

        self.objects_added_to_scene.clear()
        self.objects_removed_from_scene.clear()
        self.collections_added_to_scene.clear()
        self.collections_removed_from_scene.clear()

        self.objects_reparented.clear()
        self.objects_renamed.clear()
        self.objects_visibility_changed.clear()
        self.clear_changed_frame_related_lists()

    def update_scenes_info(self):
        self.scenes_info = {}

        for scene in self.blender_scenes.values():
            master_collection = scene.collection
            collections = [x.name_full for x in master_collection.children]
            objects = [x.name_full for x in master_collection.objects]
            self.scenes_info[scene.name_full] = SceneInfo(collections, objects)

    def update_collections_info(self):
        self.collections_info = {}

        # All non master collections
        for collection in self.blender_collections.values():
            if not self.collections_info.get(collection.name_full):
                collection_info = CollectionInfo(
                    collection.hide_viewport,
                    collection.instance_offset,
                    [x.name_full for x in collection.children],
                    None,
                )
                self.collections_info[collection.name_full] = collection_info
            for child in collection.children:
                collection_info = CollectionInfo(
                    child.hide_viewport,
                    child.instance_offset,
                    [x.name_full for x in child.children],
                    collection.name_full,
                )
                self.collections_info[child.name_full] = collection_info

        # Store non master collections objects
        for collection in self.blender_collections.values():
            self.collections_info[collection.name_full].objects = [x.name_full for x in collection.objects]

    def update_objects_info(self):
        self.old_objects = self.blender_objects

        self.objects_transforms = {}
        for obj in self.blender_objects.values():
            self.objects_transforms[obj.name_full] = obj.matrix_local.copy()

    def update_current_data(self):
        self.update_scenes_info()
        self.update_collections_info()
        self.update_objects_info()
        self.objects_visibility = {x.name_full: object_visibility(x) for x in self.blender_objects.values()}
        self.objects_parents = {
            x.name_full: x.parent.name_full if x.parent is not None else "" for x in self.blender_objects.values()
        }


share_data = ShareData()
