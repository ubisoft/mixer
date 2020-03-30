from ..broadcaster import common
from ..shareData import shareData
import logging
import bpy

collection_logger = logging.getLogger('collection')
collection_logger.setLevel(logging.INFO)


def buildCollection(data):
    name_full, index = common.decodeString(data, 0)
    visible, index = common.decodeBool(data, index)
    hide_viewport = not visible
    offset, _ = common.decodeVector3(data, index)

    collection_logger.debug("buildCollection %s", name_full)
    collection = shareData.blenderCollections.get(name_full)
    if collection is None:
        collection = bpy.data.collections.new(name_full)
        shareData.blenderCollections[name_full] = collection
    collection.hide_viewport = hide_viewport
    collection.instance_offset = offset


def buildCollectionRemoved(data):
    name_full, index = common.decodeString(data, 0)
    collection_logger.debug("buildCollectionRemove %s", name_full)
    collection = shareData.blenderCollections[name_full]
    del shareData.blenderCollections[name_full]
    bpy.data.collections.remove(collection)


def buildCollectionToCollection(data):
    parent_name, index = common.decodeString(data, 0)
    child_name, _ = common.decodeString(data, index)
    collection_logger.debug("buildCollectionToCollection %s <- %s", parent_name, child_name)

    parent = shareData.blenderCollections[parent_name]
    child = shareData.blenderCollections[child_name]
    parent.children.link(child)


def buildRemoveCollectionFromCollection(data):
    parent_name, index = common.decodeString(data, 0)
    child_name, _ = common.decodeString(data, index)
    collection_logger.debug("buildRemoveCollectionFromCollection %s <- %s", parent_name, child_name)

    parent = shareData.blenderCollections[parent_name]
    child = shareData.blenderCollections[child_name]
    parent.children.unlink(child)


def buildAddObjectToCollection(data):
    collection_name, index = common.decodeString(data, 0)
    object_name, _ = common.decodeString(data, index)
    collection_logger.debug("buildAddObjectToCollection %s <- %s", collection_name, object_name)

    collection = shareData.blenderCollections[collection_name]

    # We may have received an object creation message before this collection link message
    # and object creation will have created and linked the collecetion if needed
    if collection.objects.get(object_name) is None:
        object_ = shareData.blenderObjects[object_name]
        collection.objects.link(object_)


def buildRemoveObjectFromCollection(data):
    collection_name, index = common.decodeString(data, 0)
    object_name, _ = common.decodeString(data, index)
    collection_logger.debug("buildRemoveObjectFromCollection %s <- %s", collection_name, object_name)

    collection = shareData.blenderCollections[collection_name]
    object_ = shareData.blenderObjects[object_name]
    collection.objects.unlink(object_)


def buildCollectionInstance(data):
    instance_name, index = common.decodeString(data, 0)
    instantiated_name, _ = common.decodeString(data, index)
    instantiated = shareData.blenderCollections[instantiated_name]

    instance = bpy.data.objects.new(name=instance_name, object_data=None)
    instance.instance_collection = instantiated
    instance.instance_type = 'COLLECTION'

    shareData.blenderObjects[instance_name] = instance
