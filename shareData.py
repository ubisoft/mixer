from datetime import datetime
import bpy

class ShareData:
    def __init__(self):
        self.runId = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.sessionId = 0  # For logging and debug
        self.client = None
        self.currentRoom = None
        self.isLocal = False
        self.localServerProcess = None
        self.selectedObjectsNames = []
        self.depsgraph = None
        self.roomListUpdateClient = None

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


shareData = ShareData()