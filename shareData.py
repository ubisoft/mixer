from typing import List, Mapping
from . import clientBlender


class ShareData:
    def __init__(self):
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
        self.objects = set()

    def clearLists(self):
        self.objectsAddedToCollection.clear()
        self.objectsRemovedFromCollection.clear()
        self.objectsReparented.clear()
        self.objectsRenamed.clear()
        self.objectsTransformed.clear()
        self.objectsVisibilityChanged.clear()


shareData = ShareData()
