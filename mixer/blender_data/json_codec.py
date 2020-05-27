import json

from mixer.blender_data.proxy import (
    BpyIDProxy,
    BpyIDRefProxy,
    BpyPropertyGroupProxy,
    BpyPropDataCollectionProxy,
    BpyPropStructCollectionProxy,
    BpyStructProxy,
    StructLikeProxy,
)

# https://stackoverflow.com/questions/38307068/make-a-dict-json-from-string-with-duplicate-keys-python/38307621#38307621
# https://stackoverflow.com/questions/31085153/easiest-way-to-serialize-object-in-a-nested-dictionary

struct_like_classes = [BpyIDProxy, BpyIDRefProxy, BpyStructProxy, BpyPropertyGroupProxy]
collection_classes = [
    BpyPropStructCollectionProxy,
    BpyPropDataCollectionProxy,
]
_classes = {c.__name__: c for c in struct_like_classes}
_classes.update({c.__name__: c for c in collection_classes})


def default(obj):
    # called top down
    class_ = obj.__class__
    is_known = issubclass(class_, StructLikeProxy) or issubclass(class_, BpyIDRefProxy) or class_ in collection_classes
    if is_known:
        d = {"__bpy_proxy_class__": class_.__name__}
        d.update(obj._data)
        return d
    return None


def decode_hook(x):
    class_name = x.get("__bpy_proxy_class__")
    class_ = _classes.get(class_name)
    if class_ is None:
        return x

    del x["__bpy_proxy_class__"]
    obj = class_()
    obj._data.update(x)
    return obj


class Codec:
    def encode(self, obj):
        return json.dumps(obj, default=default)

    def decode(self, message):
        return json.loads(message, object_hook=decode_hook)
