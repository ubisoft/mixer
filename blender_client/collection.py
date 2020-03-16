from ..broadcaster import common
from ..shareData import shareData
import logging
import bpy

collection_logger = logging.getLogger('collection')
collection_logger.setLevel(logging.DEBUG)


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


def buildCollectionToScene(data):
    name_full, _ = common.decodeString(data, 0)
    collection_logger.debug("buildCollectionToScene %s", name_full)
    collection = shareData.blenderCollections[name_full]

    # We may have received an object creation message before this collection link message
    # and object creation will have created and linked the collecetion if needed
    if bpy.context.scene.collection.children.get(collection.name) is None:
        bpy.context.scene.collection.children.link(collection)


def buildCollectionToCollection(data):
    parent_name, index = common.decodeString(data, 0)
    child_name, _ = common.decodeString(data, index)
    collection_logger.debug("buildCollectionToCollection %s <- %s", parent_name, child_name)

    parent = shareData.blenderCollections[parent_name]
    child = shareData.blenderCollections[child_name]
    parent.children.link(child)
