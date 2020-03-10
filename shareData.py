from typing import List, Mapping
from . import clientBlender
from datetime import datetime
import bpy

class CollectionInfo:
    def __init__(self, hide_viewport, instance_offset, children, parent, objects=None):
        self.hide_viewport = hide_viewport
        self.instance_offset = instance_offset
        self.children = children
        self.parent = parent
        self.objects = objects or []

class ShareData:
    def __init__(self):
        self.runId = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.sessionId = 0  # For logging and debug
        self.client: clientBlender.ClientBlender = None

        # equivalent to handlers set
        self.currentRoom: str = None

        # as received fom LIST_ALL_CLIENTS
        self.client_ids: List[Mapping[str, str]] = None

        self.isLocal = False
        self.localServerProcess = None
        self.selectedObjectsNames = []
        self.depsgraph = None

        self.objectsAdded = set()
        self.objectsRemoved = set()
        self.collectionsAdded = set()
        self.collectionsRemoved = set()
        self.objectsAddedToCollection = {}
        self.objectsRemovedFromCollection = {}
        self.collectionsAddedToCollection = set()
        self.collectionsRemovedFromCollection = set()
        self.collectionsInfo = {}
        self.objectsReparented = set()
        self.objectsParents = {}
        self.objectsRenamed = {}
        self.objectsTransformed = set()
        self.objectsTransforms = {}
        self.objectsVisibilityChanged = set()
        self.objectsVisibility = {}
        self.oldObjects = {}  # Name of object to bpy.types.Object

        self.current_statistics = None
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

        self._blenderCollections = {}
        self.blenderCollectionsDirty = True
    
    def setDirty(self):
        self.blenderObjectsDirty = True
        self.blenderMaterialsDirty = True
        self.blenderMeshesDirty = True
        self.blenderGreasePencilsDirty = True
        self.blenderCamerasDirty = True
        self.blenderLightsDirty = True
        self.blenderCollectionsDirty = True        

    def getBlenderProperty(self, property, propertyDirty, elems):
        if not propertyDirty:
            return property
        property = { x.name_full: x for x in elems }
        propertyDirty = False
        return property

    @property
    def blenderObjects(self):
        if not self.blenderObjectsDirty:
            return self._blenderObjects
        self._blenderObjects = { x.name_full: x for x in bpy.data.objects }
        self.blenderObjectsDirty = False
        return self._blenderObjects

    @property
    def blenderMaterials(self):
        if not self.blenderMaterialsDirty:
            return self._blenderMaterials
        self._blenderMaterials = { x.name_full: x for x in bpy.data.materials }
        self.blenderMaterialsDirty = False
        return self._blenderMaterials

    @property
    def blenderMeshes(self):
        if not self.blenderMeshesDirty:
            return self._blenderMeshes
        self._blenderMeshes = { x.name_full: x for x in bpy.data.meshes }
        self.blenderMeshesDirty = False
        return self._blenderMeshes

    @property
    def blenderGreasePencils(self):
        if not self.blenderGreasePencilsDirty:
            return self._blenderGreasePencils
        self._blenderGreasePencils = { x.name_full: x for x in bpy.data.grease_pencils }
        self.blenderGreasePencilsDirty = False
        return self._blenderGreasePencils

    @property
    def blenderCameras(self):
        if not self.blenderCamerasDirty:
            return self._blenderCameras
        self._blenderCameras = { x.name_full: x for x in bpy.data.cameras }
        self.blenderCamerasDirty = False
        return self._blenderCameras

    @property
    def blenderLights(self):
        if not self.blenderLightsDirty:
            return self._blenderLights
        self._blenderLights = { x.name_full: x for x in bpy.data.lights }
        self.blenderLightsDirty = False
        return self._blenderLights

    @property
    def blenderCollections(self):
        if not self.blenderCollectionsDirty:
            return self._blenderCollections
        self._blenderCollections = { x.name_full: x for x in bpy.data.collections }
        self.blenderCollectionsDirty = False
        return self._blenderCollections

    def clearChangedFrameRelatedLists(self):
        self.objectsTransformed.clear()

    def clearLists(self):
        self.objectsAddedToCollection.clear()
        self.objectsRemovedFromCollection.clear()
        self.objectsReparented.clear()
        self.objectsRenamed.clear()
        self.objectsVisibilityChanged.clear()
        self.clearChangedFrameRelatedLists()

    def updateCollectionsInfo(self):
        self.collectionsInfo = {}

        # Master Collection (scene dependent)
        collection = bpy.context.scene.collection
        children = [x.name_full for x in collection.children]
        self.collectionsInfo[collection.name_full] = CollectionInfo(
            collection.hide_viewport, collection.instance_offset, children, None, [x.name_full for x in collection.objects])
        for child in collection.children:
            self.collectionsInfo[child.name_full] = CollectionInfo(child.hide_viewport, child.instance_offset, [
                                                                x.name_full for x in child.children], collection.name_full)

        # All other collections (all scenes)
        for collection in self.blenderCollections.values():
            if not self.collectionsInfo.get(collection.name_full):
                self.collectionsInfo[collection.name_full] = CollectionInfo(collection.hide_viewport, collection.instance_offset, [
                                                                            x.name_full for x in collection.children], None)
            for child in collection.children:
                self.collectionsInfo[child.name_full] = CollectionInfo(child.hide_viewport, child.instance_offset, [
                                                                    x.name_full for x in child.children], collection.name_full)

        # Store collections objects (already done for master collection above)
        for collection in self.blenderCollections.values():
            self.collectionsInfo[collection.name_full].objects = [x.name_full for x in collection.objects]

    def updateObjectsInfo(self):
        self.oldObjects = self.blenderObjects

        self.objectsTransforms = {}
        for obj in self.blenderObjects.values():
            self.objectsTransforms[obj.name_full] = obj.matrix_local.copy()

    def updateCurrentData(self):
        self.updateCollectionsInfo()    
        self.updateObjectsInfo()    
        self.objectsVisibility = dict((x.name_full, x.hide_viewport) for x in self.blenderObjects.values())
        self.objectsParents = dict((x.name_full, x.parent.name_full if x.parent != None else "") for x in self.blenderObjects.values())


shareData = ShareData()
