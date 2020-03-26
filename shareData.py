from datetime import datetime
from typing import List, Mapping, Set

import bpy


class CollectionInfo:
    def __init__(self, hide_viewport: bool, instance_offset,
                 children: List[str],
                 parent: List[str],
                 objects: List[str] = None):
        self.hide_viewport = hide_viewport
        self.instance_offset = instance_offset
        self.children = children
        self.parent = parent
        self.objects = objects or []


class SceneInfo:
    def __init__(self,
                 children: List[str],
                 objects: List[str] = None):
        self.children = children
        self.objects = objects or []


class ShareData:
    def __init__(self):
        self.runId = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.sessionId = 0  # For logging and debug
        self.client: "clientBlender.ClientBlender" = None

        # equivalent to handlers set
        self.currentRoom: str = None

        # as received fom LIST_ALL_CLIENTS
        self.client_ids: List[Mapping[str, str]] = None

        self.isLocal = False
        self.localServerProcess = None
        self.selectedObjectsNames = []
        self.depsgraph = None

        self.objectsAdded: Set(str) = set()
        self.objectsRemoved: Set(str) = set()
        self.collectionsAdded: Set(str) = set()
        self.collectionsRemoved: Set(str) = set()
        self.scenesAdded: Set(str) = set()
        self.scenesRemoved: Set(str) = set()

        # key : collection name
        self.objectsAddedToCollection: Mapping(str, str) = {}
        self.objectsRemovedFromCollection: Mapping(str, str) = {}
        self.collectionsAddedToCollection: Set(str, str) = set()
        self.collectionsRemovedFromCollection: Set(str, str) = set()

        # key : scene name
        self.objectsAddedToScene: Mapping(str, str) = {}
        self.objectsRemovedFromScene: Mapping(str, str) = {}
        self.collectionsAddedToScene: Set(str, str) = set()
        self.collectionsRemovedFromScene: Set(str, str) = set()

        # All non master collections
        self.collectionsInfo: Mapping[str, CollectionInfo] = {}

        # Master collections
        self.scenesInfo: Mapping[str, SceneInfo] = {}

        self.objectsReparented = set()
        self.objectsParents = {}
        self.objectsRenamed = {}
        self.objectsTransformed = set()
        self.objectsTransforms = {}
        self.objectsVisibilityChanged = set()
        self.objectsVisibility = {}

        self.oldObjects: Mapping[str, bpy.types.Object] = {}

        # {objectPath: [collectionName]}
        self.restoreToCollections: Mapping[str, List[str]] = {}

        self.current_statistics = None
        self.current_stats_timer = None
        self.auto_save_statistics = False
        self.statistics_directory = None

        self._blenderObjects = {}
        self.blenderObjectsDirty = True

        self._blenderMaterials = {}
        self.blenderMaterialsDirty = True

        self._blenderMeshes = {}
        self.blenderMeshesDirty = True

        self._blenderGreasePencils = {}
        self.blenderGreasePencilsDirty = True

        self._blenderCameras = {}
        self.blenderCamerasDirty = True

        self._blenderLights = {}
        self.blenderLightsDirty = True
        self._blenderCollections: Mapping[str, bpy.types.Collection] = {}
        self.blenderCollectionsDirty = True

        self._blenderScenes: Mapping[str, bpy.types.Scene] = {}
        self.blenderScenesDirty = True

    def clearBeforeState(self):
        # These objects contain the "before" state when entering the update_post handler
        # They must be empty before the first update so that the whole scene is sent
        self.oldObjects = {}
        self.collectionsInfo = {}
        self.scenesInfo = {}

    def setDirty(self):
        self.blenderObjectsDirty = True
        self.blenderMaterialsDirty = True
        self.blenderMeshesDirty = True
        self.blenderGreasePencilsDirty = True
        self.blenderCamerasDirty = True
        self.blenderLightsDirty = True
        self.blenderCollectionsDirty = True
        self.blenderScenesDirty = True

    def getBlenderProperty(self, property, propertyDirty, elems):
        if not propertyDirty:
            return property
        property = {x.name_full: x for x in elems}
        propertyDirty = False
        return property

    @property
    def blenderObjects(self):
        if not self.blenderObjectsDirty:
            return self._blenderObjects
        self._blenderObjects = {x.name_full: x for x in bpy.data.objects}
        self.blenderObjectsDirty = False
        return self._blenderObjects

    @property
    def blenderMaterials(self):
        if not self.blenderMaterialsDirty:
            return self._blenderMaterials
        self._blenderMaterials = {x.name_full: x for x in bpy.data.materials}
        self.blenderMaterialsDirty = False
        return self._blenderMaterials

    @property
    def blenderMeshes(self):
        if not self.blenderMeshesDirty:
            return self._blenderMeshes
        self._blenderMeshes = {x.name_full: x for x in bpy.data.meshes}
        self.blenderMeshesDirty = False
        return self._blenderMeshes

    @property
    def blenderGreasePencils(self):
        if not self.blenderGreasePencilsDirty:
            return self._blenderGreasePencils
        self._blenderGreasePencils = {x.name_full: x for x in bpy.data.grease_pencils}
        self.blenderGreasePencilsDirty = False
        return self._blenderGreasePencils

    @property
    def blenderCameras(self):
        if not self.blenderCamerasDirty:
            return self._blenderCameras
        self._blenderCameras = {x.name_full: x for x in bpy.data.cameras}
        self.blenderCamerasDirty = False
        return self._blenderCameras

    @property
    def blenderLights(self):
        if not self.blenderLightsDirty:
            return self._blenderLights
        self._blenderLights = {x.name_full: x for x in bpy.data.lights}
        self.blenderLightsDirty = False
        return self._blenderLights

    @property
    def blenderCollections(self):
        if not self.blenderCollectionsDirty:
            return self._blenderCollections
        self._blenderCollections = {x.name_full: x for x in bpy.data.collections}
        self.blenderCollectionsDirty = False
        return self._blenderCollections

    @property
    def blenderScenes(self):
        if not self.blenderScenesDirty:
            return self._blenderScenes
        self._blenderScenes = {x.name_full: x for x in bpy.data.scenes}
        self.blenderScenesDirty = False
        return self._blenderScenes

    def clearChangedFrameRelatedLists(self):
        self.objectsTransformed.clear()

    def clearLists(self):
        """
        Clear the lists that record change between previous and current state
        """
        self.scenesAdded.clear()
        self.scenesRemoved.clear()

        self.collectionsAdded.clear()
        self.collectionsRemoved.clear()

        self.collectionsAddedToCollection.clear()
        self.collectionsRemovedFromCollection.clear()
        self.objectsAddedToCollection.clear()
        self.objectsRemovedFromCollection.clear()

        self.objectsAddedToScene.clear()
        self.objectsRemovedFromScene.clear()
        self.collectionsAddedToScene.clear()
        self.collectionsRemovedFromScene.clear()

        self.objectsReparented.clear()
        self.objectsRenamed.clear()
        self.objectsVisibilityChanged.clear()
        self.clearChangedFrameRelatedLists()

    def updateScenesInfo(self):
        self.scenesInfo = {}

        for scene in self.blenderScenes.values():
            masterCollection = scene.collection
            collections = [x.name_full for x in masterCollection.children]
            objects = [x.name_full for x in masterCollection.objects]
            sInfo = SceneInfo(collections, objects)
            self.scenesInfo[scene.name_full] = sInfo

    def updateCollectionsInfo(self):
        self.collectionsInfo = {}

        # All non master collections
        for collection in self.blenderCollections.values():
            if not self.collectionsInfo.get(collection.name_full):
                cInfo = CollectionInfo(collection.hide_viewport, collection.instance_offset,
                                       [x.name_full for x in collection.children], None)
                self.collectionsInfo[collection.name_full] = cInfo
            for child in collection.children:
                cInfo = CollectionInfo(child.hide_viewport, child.instance_offset,
                                       [x.name_full for x in child.children], collection.name_full)
                self.collectionsInfo[child.name_full] = cInfo

        # Store non master collections objects
        for collection in self.blenderCollections.values():
            self.collectionsInfo[collection.name_full].objects = [x.name_full for x in collection.objects]

    def updateObjectsInfo(self):
        self.oldObjects = self.blenderObjects

        self.objectsTransforms = {}
        for obj in self.blenderObjects.values():
            self.objectsTransforms[obj.name_full] = obj.matrix_local.copy()

    def updateCurrentData(self):
        self.updateScenesInfo()
        self.updateCollectionsInfo()
        self.updateObjectsInfo()
        self.objectsVisibility = dict((x.name_full, x.hide_viewport) for x in self.blenderObjects.values())
        self.objectsParents = dict((x.name_full, x.parent.name_full if x.parent is not None else "")
                                   for x in self.blenderObjects.values())


shareData = ShareData()
