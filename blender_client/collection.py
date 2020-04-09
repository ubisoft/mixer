from ..broadcaster import common
from ..shareData import shareData
import logging
import bpy

logger = logging.getLogger(__name__)


def sendCollection(client: 'ClientBlender', collection: bpy.types.Collection):
    logger.debug("sendCollection %s", collection.name_full)
    collectionInstanceOffset = collection.instance_offset
    buffer = common.encodeString(collection.name_full) + common.encodeBool(not collection.hide_viewport) + \
        common.encodeVector3(collectionInstanceOffset)
    client.addCommand(common.Command(
        common.MessageType.COLLECTION, buffer, 0))


def buildCollection(data):
    name_full, index = common.decodeString(data, 0)
    visible, index = common.decodeBool(data, index)
    hide_viewport = not visible
    offset, _ = common.decodeVector3(data, index)

    logger.debug("buildCollection %s", name_full)
    collection = shareData.blenderCollections.get(name_full)
    if collection is None:
        collection = bpy.data.collections.new(name_full)
        shareData.blenderCollections[name_full] = collection
    collection.hide_viewport = hide_viewport
    collection.instance_offset = offset


def sendCollectionRemoved(client: 'ClientBlender', collectionName):
    logger.debug("sendCollectionRemoved %s", collectionName)
    buffer = common.encodeString(collectionName)
    client.addCommand(common.Command(
        common.MessageType.COLLECTION_REMOVED, buffer, 0))


def buildCollectionRemoved(data):
    name_full, index = common.decodeString(data, 0)
    logger.debug("buildCollectionRemove %s", name_full)
    collection = shareData.blenderCollections[name_full]
    del shareData.blenderCollections[name_full]
    bpy.data.collections.remove(collection)


def sendAddCollectionToCollection(client: 'ClientBlender', parentCollectionName, collectionName):
    logger.debug("sendAddCollectionToCollection %s <- %s", parentCollectionName, collectionName)

    buffer = common.encodeString(
        parentCollectionName) + common.encodeString(collectionName)
    client.addCommand(common.Command(
        common.MessageType.ADD_COLLECTION_TO_COLLECTION, buffer, 0))


def buildCollectionToCollection(data):
    parent_name, index = common.decodeString(data, 0)
    child_name, _ = common.decodeString(data, index)
    logger.debug("buildCollectionToCollection %s <- %s", parent_name, child_name)

    parent = shareData.blenderCollections[parent_name]
    child = shareData.blenderCollections[child_name]
    parent.children.link(child)


def sendRemoveCollectionFromCollection(client: 'ClientBlender', parentCollectionName, collectionName):
    logger.debug("sendRemoveCollectionFromCollection %s <- %s", parentCollectionName, collectionName)

    buffer = common.encodeString(
        parentCollectionName) + common.encodeString(collectionName)
    client.addCommand(common.Command(
        common.MessageType.REMOVE_COLLECTION_FROM_COLLECTION, buffer, 0))


def buildRemoveCollectionFromCollection(data):
    parent_name, index = common.decodeString(data, 0)
    child_name, _ = common.decodeString(data, index)
    logger.debug("buildRemoveCollectionFromCollection %s <- %s", parent_name, child_name)

    parent = shareData.blenderCollections[parent_name]
    child = shareData.blenderCollections[child_name]
    parent.children.unlink(child)


def sendAddObjectToCollection(client: 'ClientBlender', collectionName, objName):
    logger.debug("sendAddObjectToCollection %s <- %s", collectionName, objName)
    buffer = common.encodeString(
        collectionName) + common.encodeString(objName)
    client.addCommand(common.Command(
        common.MessageType.ADD_OBJECT_TO_COLLECTION, buffer, 0))


def buildAddObjectToCollection(data):
    collection_name, index = common.decodeString(data, 0)
    object_name, _ = common.decodeString(data, index)
    logger.debug("buildAddObjectToCollection %s <- %s", collection_name, object_name)

    collection = shareData.blenderCollections[collection_name]

    # We may have received an object creation message before this collection link message
    # and object creation will have created and linked the collecetion if needed
    if collection.objects.get(object_name) is None:
        object_ = shareData.blenderObjects[object_name]
        collection.objects.link(object_)


def sendRemoveObjectFromCollection(client: 'ClientBlender', collectionName, objName):
    logger.debug("sendRemoveObjectFromCollection %s <- %s", collectionName, objName)
    buffer = common.encodeString(
        collectionName) + common.encodeString(objName)
    client.addCommand(common.Command(
        common.MessageType.REMOVE_OBJECT_FROM_COLLECTION, buffer, 0))


def buildRemoveObjectFromCollection(data):
    collection_name, index = common.decodeString(data, 0)
    object_name, _ = common.decodeString(data, index)
    logger.debug("buildRemoveObjectFromCollection %s <- %s", collection_name, object_name)

    collection = shareData.blenderCollections[collection_name]
    object_ = shareData.blenderObjects[object_name]
    collection.objects.unlink(object_)


def sendCollectionInstance(client: 'ClientBlender', obj):
    if not obj.instance_collection:
        return
    instanceName = obj.name_full
    instantiatedCollection = obj.instance_collection.name_full
    buffer = common.encodeString(
        instanceName) + common.encodeString(instantiatedCollection)
    client.addCommand(common.Command(
        common.MessageType.INSTANCE_COLLECTION, buffer, 0))


def buildCollectionInstance(data):
    instance_name, index = common.decodeString(data, 0)
    instantiated_name, _ = common.decodeString(data, index)
    instantiated = shareData.blenderCollections[instantiated_name]

    instance = bpy.data.objects.new(name=instance_name, object_data=None)
    instance.instance_collection = instantiated
    instance.instance_type = 'COLLECTION'

    shareData.blenderObjects[instance_name] = instance
