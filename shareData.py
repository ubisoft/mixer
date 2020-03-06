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
        return self.getBlenderProperty(self._blenderObjects, self.blenderObjectsDirty, bpy.data.objects)

    @property
    def blenderMaterials(self):
        return self.getBlenderProperty(self._blenderMaterials, self.blenderMaterialsDirty, bpy.data.materials)

    @property
    def blenderMeshes(self):
        return self.getBlenderProperty(self._blenderMeshes, self.blenderMeshesDirty, bpy.data.meshes)

    @property
    def blenderGreasePencils(self):
        return self.getBlenderProperty(self._blenderGreasePencils, self.blenderGreasePencilsDirty, bpy.data.grease_pencils)

    @property
    def blenderCameras(self):
        return self.getBlenderProperty(self._blenderCameras, self.blenderCamerasDirty, bpy.data.cameras)

    @property
    def blenderLights(self):
        return self.getBlenderProperty(self._blenderLights, self.blenderLightsDirty, bpy.data.lights)

    @property
    def blenderCollections(self):
        return self.getBlenderProperty(self._blenderCollections, self.blenderCollectionsDirty, bpy.data.collections)
    def clearLists(self):
        self.objectsAddedToCollection.clear()
        self.objectsRemovedFromCollection.clear()
        self.objectsReparented.clear()
        self.objectsRenamed.clear()
        self.objectsTransformed.clear()
        self.objectsVisibilityChanged.clear()


shareData = ShareData()