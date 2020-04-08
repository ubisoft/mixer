import logging
import struct
import os

import bpy
from mathutils import Matrix, Quaternion
from . import ui
from . import data
from .shareData import shareData
from .broadcaster import common
from .broadcaster.client import Client
from .blender_client import collection as collection_api
from .blender_client import scene as scene_api
from .blender_client import mesh as mesh_api
from .stats import stats_timer

_STILL_ACTIVE = 259


logger = logging.getLogger(__name__)


class ClientBlender(Client):
    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        super(ClientBlender, self).__init__(
            host, port)

        self.textures = set()
        self.callbacks = {}

        self.blenderPID = os.getpid()

    def addCallback(self, name, func):
        self.callbacks[name] = func

    # returns the path of an object
    def getObjectPath(self, obj):
        path = obj.name_full
        while obj.parent:
            obj = obj.parent
            if obj:
                path = obj.name_full + "/" + path
        return path

    # get first collection
    def getOrCreateCollection(self, name: str):
        collection = shareData.blenderCollections.get(name)
        if not collection:
            bpy.ops.collection.create(name=name)
            collection = bpy.data.collections[name]
            shareData._blenderCollections[name] = collection
            bpy.context.scene.collection.children.link(collection)
        return collection

    def getOrCreatePath(self, path, data=None) -> bpy.types.Object:
        index = path.rfind('/')
        if index != -1:
            shareData.pendingParenting.add(path)  # Parenting is resolved after consumption of all messages

        # Create or get object
        elem = path[index + 1:]
        ob = shareData.blenderObjects.get(elem)
        if not ob:
            ob = bpy.data.objects.new(elem, data)
            shareData._blenderObjects[ob.name_full] = ob
        return ob

    def getOrCreateObjectData(self, path, data):
        return self.getOrCreatePath(path, data)

    def getOrCreateCamera(self, cameraName):
        camera = shareData.blenderCameras.get(cameraName)
        if camera:
            return camera
        camera = bpy.data.cameras.new(cameraName)
        shareData._blenderCameras[camera.name_full] = camera
        return camera

    def buildCamera(self, data):
        cameraPath, start = common.decodeString(data, 0)

        cameraName = cameraPath.split('/')[-1]
        camera = self.getOrCreateCamera(cameraName)

        camera.lens, start = common.decodeFloat(data, start)
        camera.clip_start, start = common.decodeFloat(data, start)
        camera.clip_end, start = common.decodeFloat(data, start)
        camera.dof.aperture_fstop, start = common.decodeFloat(data, start)
        sensorFit, start = common.decodeInt(data, start)
        camera.sensor_width, start = common.decodeFloat(data, start)
        camera.sensor_height, start = common.decodeFloat(data, start)

        if sensorFit == 0:
            camera.sensor_fit = 'AUTO'
        elif sensorFit == 1:
            camera.sensor_fit = 'VERTICAL'
        else:
            camera.sensor_fit = 'HORIZONTAL'

        self.getOrCreateObjectData(cameraPath, camera)

    def getOrCreateLight(self, lightName, lightType):
        light = shareData.blenderLights.get(lightName)
        if light:
            return light
        light = bpy.data.lights.new(lightName, type=lightType)
        shareData._blenderLights[light.name_full] = light
        return light

    def buildLight(self, data):
        lightPath, start = common.decodeString(data, 0)
        lightType, start = common.decodeInt(data, start)
        blighttype = 'POINT'
        if lightType == common.LightType.SUN.value:
            blighttype = 'SUN'
        elif lightType == common.LightType.POINT.value:
            blighttype = 'POINT'
        else:
            blighttype = 'SPOT'

        lightName = lightPath.split('/')[-1]
        light = self.getOrCreateLight(lightName, blighttype)

        shadow, start = common.decodeInt(data, start)
        if shadow != 0:
            light.use_shadow = True
        else:
            light.use_shadow = False

        color, start = common.decodeColor(data, start)
        light.color = (color[0], color[1], color[2])
        light.energy, start = common.decodeFloat(data, start)
        if lightType == common.LightType.SPOT.value:
            light.spot_size, start = common.decodeFloat(data, start)
            light.spot_blend, start = common.decodeFloat(data, start)

        self.getOrCreateObjectData(lightPath, light)

    def getOrCreateMesh(self, meshName):
        me = shareData.blenderMeshes.get(meshName)
        if not me:
            me = bpy.data.meshes.new(meshName)
            shareData._blenderMeshes[me.name_full] = me
        return me

    def setTransform(self, obj, parentInverseMatrix, basisMatrix, localMatrix):
        obj.matrix_parent_inverse = parentInverseMatrix
        obj.matrix_basis = basisMatrix
        obj.matrix_local = localMatrix

    def buildMatrixFromComponents(self, translate, rotate, scale):
        t = Matrix.Translation(translate)
        r = Quaternion(rotate).to_matrix().to_4x4()
        s = Matrix()
        s[0][0] = scale[0]
        s[1][1] = scale[1]
        s[2][2] = scale[2]
        return s @ r @ t

    def decodeMatrix(self, data, index):
        matrix_data, index = common.decodeMatrix(data, index)
        m = Matrix()
        m.col[0] = matrix_data[0]
        m.col[1] = matrix_data[1]
        m.col[2] = matrix_data[2]
        m.col[3] = matrix_data[3]
        return m, index

    def buildTransform(self, data):
        start = 0
        objectPath, start = common.decodeString(data, start)
        parentInvertMatrix, start = self.decodeMatrix(data, start)
        basisMatrix, start = self.decodeMatrix(data, start)
        localMatrix, start = self.decodeMatrix(data, start)
        visible, start = common.decodeBool(data, start)

        try:
            obj = self.getOrCreatePath(objectPath)
        except KeyError:
            # Object doesn't exist anymore
            return
        if obj:
            self.setTransform(obj, parentInvertMatrix, basisMatrix, localMatrix)
            obj.hide_viewport = not visible

    def getOrCreateMaterial(self, materialName):
        material = shareData.blenderMaterials.get(materialName)
        if material:
            material.use_nodes = True
            return material

        material = bpy.data.materials.new(name=materialName)
        shareData._blenderMaterials[material.name_full] = material
        material.use_nodes = True
        return material

    def buildTexture(self, principled, material, channel, isColor, data, index):
        fileName, index = common.decodeString(data, index)
        if len(fileName) > 0:
            texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
            try:
                texImage.image = bpy.data.images.load(fileName)
                if not isColor:
                    texImage.image.colorspace_settings.name = 'Non-Color'
            except Exception as e:
                logger.error(e)
            material.node_tree.links.new(
                principled.inputs[channel], texImage.outputs['Color'])
        return index

    def buildMaterial(self, data):
        materialNameLength = common.bytesToInt(data[:4])
        start = 4
        end = start + materialNameLength
        materialName = data[start:end].decode()
        start = end

        material = self.getOrCreateMaterial(materialName)
        nodes = material.node_tree.nodes
        # Get a principled node
        principled = None
        if nodes:
            for n in nodes:
                if n.type == 'BSDF_PRINCIPLED':
                    principled = n
                    break

        if not principled:
            logger.error("Cannot find Principled BSDF node")
            return

        index = start

        # Transmission ( 1 - opacity)
        transmission, index = common.decodeFloat(data, index)
        transmission = 1 - transmission
        principled.inputs['Transmission'].default_value = transmission
        fileName, index = common.decodeString(data, index)
        if len(fileName) > 0:
            invert = material.node_tree.nodes.new('ShaderNodeInvert')
            material.node_tree.links.new(
                principled.inputs['Transmission'], invert.outputs['Color'])
            texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
            try:
                texImage.image = bpy.data.images.load(fileName)
                texImage.image.colorspace_settings.name = 'Non-Color'
            except Exception as e:
                logger.error("could not load file %s (%s)", fileName, e)
            material.node_tree.links.new(
                invert.inputs['Color'], texImage.outputs['Color'])

        # Base Color
        baseColor, index = common.decodeColor(data, index)
        material.diffuse_color = (baseColor[0], baseColor[1], baseColor[2], 1)
        principled.inputs['Base Color'].default_value = material.diffuse_color
        index = self.buildTexture(
            principled, material, 'Base Color', True, data, index)

        # Metallic
        material.metallic, index = common.decodeFloat(data, index)
        principled.inputs['Metallic'].default_value = material.metallic
        index = self.buildTexture(
            principled, material, 'Metallic', False, data, index)

        # Roughness
        material.roughness, index = common.decodeFloat(data, index)
        principled.inputs['Roughness'].default_value = material.roughness
        index = self.buildTexture(
            principled, material, 'Roughness', False, data, index)

        # Normal
        fileName, index = common.decodeString(data, index)
        if len(fileName) > 0:
            normalMap = material.node_tree.nodes.new('ShaderNodeNormalMap')
            material.node_tree.links.new(
                principled.inputs['Normal'], normalMap.outputs['Normal'])
            texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
            try:
                texImage.image = bpy.data.images.load(fileName)
                texImage.image.colorspace_settings.name = 'Non-Color'
            except Exception as e:
                logger.error("could not load file %s (%s)", fileName, e)
            material.node_tree.links.new(
                normalMap.inputs['Color'], texImage.outputs['Color'])

        # Emission
        emission, index = common.decodeColor(data, index)
        principled.inputs['Emission'].default_value = emission
        index = self.buildTexture(
            principled, material, 'Emission', False, data, index)

    def buildRename(self, data):
        oldPath, index = common.decodeString(data, 0)
        newPath, index = common.decodeString(data, index)
        oldName = oldPath.split('/')[-1]
        newName = newPath.split('/')[-1]
        shareData.blenderObjects.get(oldName).name = newName

    def buildDuplicate(self, data):
        srcPath, index = common.decodeString(data, 0)
        dstName, index = common.decodeString(data, index)
        basisMatrix, index = self.decodeMatrix(data, index)

        try:
            obj = self.getOrCreatePath(srcPath)
            newObj = obj.copy()
            newObj.name = dstName
            if hasattr(obj, "data"):
                newObj.data = obj.data.copy()
                newObj.animation_data_clear()
            for collection in obj.users_collection:
                collection.objects.link(newObj)

            self.setTransform(newObj, obj.matrix_parent_invert, basisMatrix, obj.matrix_parent_invert @ basisMatrix)
        except Exception:
            pass

    def buildDelete(self, data):
        path, _ = common.decodeString(data, 0)

        try:
            obj = shareData.blenderObjects[path.split('/')[-1]]
        except KeyError:
            # Object doesn't exist anymore
            return
        del shareData._blenderObjects[obj.name_full]
        bpy.data.objects.remove(obj, do_unlink=True)

    def buildSendToTrash(self, data):
        path, _ = common.decodeString(data, 0)
        obj = self.getOrCreatePath(path)

        shareData.restoreToCollections[obj.name_full] = []
        restoreTo = shareData.restoreToCollections[obj.name_full]
        for collection in obj.users_collection:
            restoreTo.append(collection.name_full)
            collection.objects.unlink(obj)
        # collection = self.getOrCreateCollection()
        # collection.objects.unlink(obj)
        trashCollection = self.getOrCreateCollection("__Trash__")
        trashCollection.hide_viewport = True
        trashCollection.objects.link(obj)

    def buildRestoreFromTrash(self, data):
        name, index = common.decodeString(data, 0)
        path, index = common.decodeString(data, index)

        obj = shareData.blenderObjects[name]
        trashCollection = self.getOrCreateCollection("__Trash__")
        trashCollection.hide_viewport = True
        trashCollection.objects.unlink(obj)
        restoreTo = shareData.restoreToCollections[obj.name_full]
        for collectionName in restoreTo:
            collection = self.getOrCreateCollection(collectionName)
            collection.objects.link(obj)
        del shareData.restoreToCollections[obj.name_full]
        if len(path) > 0:
            parentName = path.split('/')[-1]
            obj.parent = shareData.blenderObjects.get(parentName, None)

    def getTransformBuffer(self, obj):
        path = self.getObjectPath(obj)
        visible = not obj.hide_viewport
        return common.encodeString(path) + common.encodeMatrix(obj.matrix_parent_inverse) + \
            common.encodeMatrix(obj.matrix_basis) + common.encodeMatrix(obj.matrix_local) + common.encodeBool(visible)

    def sendTransform(self, obj):
        transformBuffer = self.getTransformBuffer(obj)
        self.addCommand(common.Command(
            common.MessageType.TRANSFORM, transformBuffer, 0))

    def buildTextureFile(self, data):
        path, index = common.decodeString(data, 0)
        if not os.path.exists(path):
            size, index = common.decodeInt(data, index)
            try:
                f = open(path, "wb")
                f.write(data[index:index+size])
                f.close()
                self.textures.add(path)
            except Exception as e:
                logger.error("could not write file %s (%s)", path, e)

    def sendTextureFile(self, path):
        if path in self.textures:
            return
        if os.path.exists(path):
            try:
                f = open(path, "rb")
                data = f.read()
                f.close()
                self.sendTextureData(path, data)
            except Exception as e:
                logger.error("could not read file %s (%s)", path, e)

    def sendTextureData(self, path, data):
        nameBuffer = common.encodeString(path)
        self.textures.add(path)
        self.addCommand(common.Command(common.MessageType.TEXTURE,
                                       nameBuffer + common.encodeInt(len(data)) + data, 0))

    def getTexture(self, inputs):
        if not inputs:
            return None
        if len(inputs.links) == 1:
            connectedNode = inputs.links[0].from_node
            if type(connectedNode).__name__ == 'ShaderNodeTexImage':
                image = connectedNode.image
                pack = image.packed_file
                path = bpy.path.abspath(image.filepath)
                path = path.replace("\\", "/")
                if pack:
                    self.sendTextureData(path, pack.data)
                else:
                    self.sendTextureFile(path)
                return path
        return None

    def getMaterialBuffer(self, material):
        name = material.name_full
        buffer = common.encodeString(name)
        principled = None
        diffuse = None
        # Get the nodes in the node tree
        if material.node_tree:
            nodes = material.node_tree.nodes
            # Get a principled node
            if nodes:
                for n in nodes:
                    if n.type == 'BSDF_PRINCIPLED':
                        principled = n
                        break
                    if n.type == 'BSDF_DIFFUSE':
                        diffuse = n
            # principled = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        if principled is None and diffuse is None:
            baseColor = (0.8, 0.8, 0.8)
            metallic = 0.0
            roughness = 0.5
            opacity = 1.0
            emissionColor = (0.0, 0.0, 0.0)
            buffer += common.encodeFloat(opacity) + common.encodeString("")
            buffer += common.encodeColor(baseColor) + common.encodeString("")
            buffer += common.encodeFloat(metallic) + common.encodeString("")
            buffer += common.encodeFloat(roughness) + common.encodeString("")
            buffer += common.encodeString("")
            buffer += common.encodeColor(emissionColor) + \
                common.encodeString("")
            return buffer
        elif diffuse:
            opacity = 1.0
            opacityTexture = None
            metallic = 0.0
            metallicTexture = None
            emission = (0.0, 0.0, 0.0)
            emissionTexture = None

            # Get the slot for 'base color'
            # Or principled.inputs[0]
            baseColor = (1.0, 1.0, 1.0)
            baseColorTexture = None
            baseColorInput = diffuse.inputs.get('Color')
            # Get its default value (not the value from a possible link)
            if baseColorInput:
                baseColor = baseColorInput.default_value
                baseColorTexture = self.getTexture(baseColorInput)

            roughness = 1.0
            roughnessTexture = None
            roughnessInput = diffuse.inputs.get('Roughness')
            if roughnessInput:
                roughnessTexture = self.getTexture(roughnessInput)
                if len(roughnessInput.links) == 0:
                    roughness = roughnessInput.default_value

            normalTexture = None
            normalInput = diffuse.inputs.get('Normal')
            if normalInput:
                if len(normalInput.links) == 1:
                    normalMap = normalInput.links[0].from_node
                    if "Color" in normalMap.inputs:
                        colorInput = normalMap.inputs["Color"]
                        normalTexture = self.getTexture(colorInput)

        else:
            opacity = 1.0
            opacityTexture = None
            opacityInput = principled.inputs.get('Transmission')
            if opacityInput:
                if len(opacityInput.links) == 1:
                    invert = opacityInput.links[0].from_node
                    if "Color" in invert.inputs:
                        colorInput = invert.inputs["Color"]
                        opacityTexture = self.getTexture(colorInput)
                else:
                    opacity = 1.0 - opacityInput.default_value

            # Get the slot for 'base color'
            # Or principled.inputs[0]
            baseColor = (1.0, 1.0, 1.0)
            baseColorTexture = None
            baseColorInput = principled.inputs.get('Base Color')
            # Get its default value (not the value from a possible link)
            if baseColorInput:
                baseColor = baseColorInput.default_value
                baseColorTexture = self.getTexture(baseColorInput)

            metallic = 0.0
            metallicTexture = None
            metallicInput = principled.inputs.get('Metallic')
            if metallicInput:
                metallicTexture = self.getTexture(metallicInput)
                if len(metallicInput.links) == 0:
                    metallic = metallicInput.default_value

            roughness = 1.0
            roughnessTexture = None
            roughnessInput = principled.inputs.get('Roughness')
            if roughnessInput:
                roughnessTexture = self.getTexture(roughnessInput)
                if len(roughnessInput.links) == 0:
                    roughness = roughnessInput.default_value

            normalTexture = None
            normalInput = principled.inputs.get('Normal')
            if normalInput:
                if len(normalInput.links) == 1:
                    normalMap = normalInput.links[0].from_node
                    if "Color" in normalMap.inputs:
                        colorInput = normalMap.inputs["Color"]
                        normalTexture = self.getTexture(colorInput)

            emission = (0.0, 0.0, 0.0)
            emissionTexture = None
            emissionInput = principled.inputs.get('Emission')
            if emissionInput:
                # Get its default value (not the value from a possible link)
                emission = emissionInput.default_value
                emissionTexture = self.getTexture(emissionInput)

        buffer += common.encodeFloat(opacity)
        if opacityTexture:
            buffer += common.encodeString(opacityTexture)
        else:
            buffer += common.encodeString("")
        buffer += common.encodeColor(baseColor)
        if baseColorTexture:
            buffer += common.encodeString(baseColorTexture)
        else:
            buffer += common.encodeString("")

        buffer += common.encodeFloat(metallic)
        if metallicTexture:
            buffer += common.encodeString(metallicTexture)
        else:
            buffer += common.encodeString("")

        buffer += common.encodeFloat(roughness)
        if roughnessTexture:
            buffer += common.encodeString(roughnessTexture)
        else:
            buffer += common.encodeString("")

        if normalTexture:
            buffer += common.encodeString(normalTexture)
        else:
            buffer += common.encodeString("")

        buffer += common.encodeColor(emission)
        if emissionTexture:
            buffer += common.encodeString(emissionTexture)
        else:
            buffer += common.encodeString("")

        return buffer

    def getMaterialBuffers(self, obj):
        try:
            buffers = []
            for slot in obj.material_slots[:]:
                if slot.material:
                    buffer = self.getMaterialBuffer(slot.material)
                    buffers.append(buffer)
            return buffers
        except Exception as e:
            logger.error(e)

    def sendGroupBegin(self):
        self.addCommand(common.Command(common.MessageType.GROUP_BEGIN, common.encodeInt(0)))

    def sendGroupEnd(self):
        self.addCommand(common.Command(common.MessageType.GROUP_END))

    def sendMaterial(self, material):
        if not material:
            return
        if material.grease_pencil:
            self.sendGreasePencilMaterial(material)
        else:
            self.addCommand(common.Command(
                common.MessageType.MATERIAL, self.getMaterialBuffer(material), 0))

    def getMeshName(self, mesh):
        return mesh.name_full

    @stats_timer(shareData)
    def sendMesh(self, obj):
        mesh = obj.data
        meshName = self.getMeshName(mesh)
        path = self.getObjectPath(obj)

        binary_buffer = common.encodeString(path) + common.encodeString(meshName)

        binary_buffer += mesh_api.encodeMesh(obj, data.get_dcc_sync_props().send_base_meshes,
                                             data.get_dcc_sync_props().send_baked_meshes)

        # For now include material slots in the same message, but maybe it should be a separated message
        # like Transform
        material_link_dict = {
            'OBJECT': 0,
            'DATA': 1
        }
        material_links = [material_link_dict[slot.link] for slot in obj.material_slots]
        assert(len(material_links) == len(obj.data.materials))
        binary_buffer += struct.pack(f'{len(material_links)}I', *material_links)

        for slot in obj.material_slots:
            if slot.link == 'DATA':
                binary_buffer += common.encodeString("")
            else:
                binary_buffer += common.encodeString(slot.material.name if slot.material is not None else "")

        self.addCommand(common.Command(common.MessageType.MESH, binary_buffer, 0))

    @stats_timer(shareData)
    def buildMesh(self, commandData):
        index = 0

        path, index = common.decodeString(commandData, index)
        meshName, index = common.decodeString(commandData, index)

        obj = self.getOrCreateObjectData(path, self.getOrCreateMesh(meshName))
        if obj.mode == 'EDIT':
            logger.error("Received a mesh for object %s while begin in EDIT mode, ignoring.", path)
            return

        index = mesh_api.decodeMesh(self, obj, commandData, index)

        material_slot_count = len(obj.data.materials)
        material_link_dict = [
            'OBJECT',
            'DATA'
        ]
        material_links = struct.unpack(f'{material_slot_count}I', commandData[index: index + 4 * material_slot_count])
        for link, slot in zip(material_links, obj.material_slots):
            slot.link = material_link_dict[link]
        index += 4 * material_slot_count

        for slot in obj.material_slots:
            material_name, index = common.decodeString(commandData, index)
            if slot.link == 'OBJECT' and material_name != "":
                slot.material = self.getOrCreateMaterial(material_name)

    def sendCollectionInstance(self, obj):
        if not obj.instance_collection:
            return
        instanceName = obj.name_full
        instantiatedCollection = obj.instance_collection.name_full
        buffer = common.encodeString(
            instanceName) + common.encodeString(instantiatedCollection)
        self.addCommand(common.Command(
            common.MessageType.INSTANCE_COLLECTION, buffer, 0))

    def sendSetCurrentScene(self, name):
        buffer = common.encodeString(name)
        self.addCommand(common.Command(
            common.MessageType.SET_SCENE, buffer, 0))

    def sendAnimationBuffer(self, objName, animationData, channelName, channelIndex=-1):
        if not animationData:
            return
        action = animationData.action
        if not action:
            return
        for fcurve in action.fcurves:
            if fcurve.data_path == channelName:
                if channelIndex == -1 or fcurve.array_index == channelIndex:
                    keyCount = len(fcurve.keyframe_points)
                    keys = []
                    for keyframe in fcurve.keyframe_points:
                        keys.extend(keyframe.co)
                    buffer = common.encodeString(objName) + common.encodeString(channelName) + common.encodeInt(
                        channelIndex) + common.intToBytes(keyCount, 4) + struct.pack(f'{len(keys)}f', *keys)
                    self.addCommand(common.Command(
                        common.MessageType.CAMERA_ANIMATION, buffer, 0))
                    return

    def sendCameraAnimations(self, obj):
        self.sendAnimationBuffer(
            obj.name_full, obj.animation_data, 'location', 0)
        self.sendAnimationBuffer(
            obj.name_full, obj.animation_data, 'location', 1)
        self.sendAnimationBuffer(
            obj.name_full, obj.animation_data, 'location', 2)
        self.sendAnimationBuffer(
            obj.name_full, obj.animation_data, 'rotation', 0)
        self.sendAnimationBuffer(
            obj.name_full, obj.animation_data, 'rotation', 1)
        self.sendAnimationBuffer(
            obj.name_full, obj.animation_data, 'rotation', 2)
        self.sendAnimationBuffer(
            obj.name_full, obj.data.animation_data, 'lens')

    def getCameraBuffer(self, obj):
        cam = obj.data
        focal = cam.lens
        frontClipPlane = cam.clip_start
        farClipPlane = cam.clip_end
        aperture = cam.dof.aperture_fstop
        sensorFitName = cam.sensor_fit
        sensorFit = common.SensorFitMode.AUTO
        if sensorFitName == 'AUTO':
            sensorFit = common.SensorFitMode.AUTO
        elif sensorFitName == 'HORIZONTAL':
            sensorFit = common.SensorFitMode.HORIZONTAL
        elif sensorFitName == 'VERTICAL':
            sensorFit = common.SensorFitMode.VERTICAL
        sensorWidth = cam.sensor_width
        sensorHeight = cam.sensor_height

        path = self.getObjectPath(obj)
        return common.encodeString(path) + \
            common.encodeFloat(focal) + \
            common.encodeFloat(frontClipPlane) + \
            common.encodeFloat(farClipPlane) + \
            common.encodeFloat(aperture) + \
            common.encodeInt(sensorFit.value) + \
            common.encodeFloat(sensorWidth) + \
            common.encodeFloat(sensorHeight)

    def sendCamera(self, obj):
        cameraBuffer = self.getCameraBuffer(obj)
        if cameraBuffer:
            self.addCommand(common.Command(
                common.MessageType.CAMERA, cameraBuffer, 0))
        self.sendCameraAnimations(obj)

    def getLightBuffer(self, obj):
        light = obj.data
        lightTypeName = light.type
        lightType = common.LightType.SUN
        if lightTypeName == 'POINT':
            lightType = common.LightType.POINT
        elif lightTypeName == 'SPOT':
            lightType = common.LightType.SPOT
        elif lightTypeName == 'SUN':
            lightType = common.LightType.SUN
        else:
            return None
        color = light.color
        power = light.energy
        if bpy.context.scene.render.engine == 'CYCLES':
            shadow = light.cycles.cast_shadow
        else:
            shadow = light.use_shadow

        spotBlend = 10.0
        spotSize = 0.0
        if lightType == common.LightType.SPOT:
            spotSize = light.spot_size
            spotBlend = light.spot_blend

        return common.encodeString(self.getObjectPath(obj)) + \
            common.encodeInt(lightType.value) + \
            common.encodeInt(shadow) + \
            common.encodeColor(color) + \
            common.encodeFloat(power) + \
            common.encodeFloat(spotSize) + \
            common.encodeFloat(spotBlend)

    def sendLight(self, obj):
        lightBuffer = self.getLightBuffer(obj)
        if lightBuffer:
            self.addCommand(common.Command(
                common.MessageType.LIGHT, lightBuffer, 0))

    def sendAddCollectionToCollection(self, parentCollectionName, collectionName):
        collection_api.logger.debug("sendAddCollectionToCollection %s <- %s", parentCollectionName, collectionName)

        buffer = common.encodeString(
            parentCollectionName) + common.encodeString(collectionName)
        self.addCommand(common.Command(
            common.MessageType.ADD_COLLECTION_TO_COLLECTION, buffer, 0))

    def sendRemoveCollectionFromCollection(self, parentCollectionName, collectionName):
        collection_api.logger.debug("sendRemoveCollectionFromCollection %s <- %s", parentCollectionName, collectionName)

        buffer = common.encodeString(
            parentCollectionName) + common.encodeString(collectionName)
        self.addCommand(common.Command(
            common.MessageType.REMOVE_COLLECTION_FROM_COLLECTION, buffer, 0))

    def sendAddObjectToCollection(self, collectionName, objName):
        collection_api.logger.debug("sendAddObjectToCollection %s <- %s", collectionName, objName)
        buffer = common.encodeString(
            collectionName) + common.encodeString(objName)
        self.addCommand(common.Command(
            common.MessageType.ADD_OBJECT_TO_COLLECTION, buffer, 0))

    def sendRemoveObjectFromCollection(self, collectionName, objName):
        collection_api.logger.debug("sendRemoveObjectFromCollection %s <- %s", collectionName, objName)
        buffer = common.encodeString(
            collectionName) + common.encodeString(objName)
        self.addCommand(common.Command(
            common.MessageType.REMOVE_OBJECT_FROM_COLLECTION, buffer, 0))

    def sendCollectionRemoved(self, collectionName):
        collection_api.logger.debug("sendCollectionRemoved %s", collectionName)
        buffer = common.encodeString(collectionName)
        self.addCommand(common.Command(
            common.MessageType.COLLECTION_REMOVED, buffer, 0))

    def sendCollection(self, collection):
        collection_api.logger.debug("sendCollection %s", collection.name_full)
        collectionInstanceOffset = collection.instance_offset
        buffer = common.encodeString(collection.name_full) + common.encodeBool(not collection.hide_viewport) + \
            common.encodeVector3(collectionInstanceOffset)
        self.addCommand(common.Command(
            common.MessageType.COLLECTION, buffer, 0))

    def sendDeletedObject(self, objName):
        self.sendDelete(objName)

    def sendRenamedObjects(self, oldName, newName):
        if oldName != newName:
            self.sendRename(oldName, newName)

    def getRenameBuffer(self, oldName, newName):
        encodedOldName = oldName.encode()
        encodedNewName = newName.encode()
        buffer = common.intToBytes(len(encodedOldName), 4) + encodedOldName + \
            common.intToBytes(len(encodedNewName), 4) + encodedNewName
        return buffer

    def sendRename(self, oldName, newName):
        self.addCommand(common.Command(common.MessageType.RENAME,
                                       self.getRenameBuffer(oldName, newName), 0))

    # -----------------------------------------------------------------------------------------------------------
    #
    # Grease Pencil
    #
    # -----------------------------------------------------------------------------------------------------------

    def sendGreasePencilStroke(self, stroke):
        buffer = common.encodeInt(stroke.material_index)
        buffer += common.encodeInt(stroke.line_width)

        points = list()

        for point in stroke.points:
            points.extend(point.co)
            points.append(point.pressure)
            points.append(point.strength)

        binaryPointsBuffer = common.intToBytes(
            len(stroke.points), 4) + struct.pack(f'{len(points)}f', *points)
        buffer += binaryPointsBuffer
        return buffer

    def sendGreasePenciFrame(self, frame):
        buffer = common.encodeInt(frame.frame_number)
        buffer += common.encodeInt(len(frame.strokes))
        for stroke in frame.strokes:
            buffer += self.sendGreasePencilStroke(stroke)
        return buffer

    def sendGreasePencilLayer(self, layer, name):
        buffer = common.encodeString(name)
        buffer += common.encodeBool(layer.hide)
        buffer += common.encodeInt(len(layer.frames))
        for frame in layer.frames:
            buffer += self.sendGreasePenciFrame(frame)
        return buffer

    def sendGreasePencilTimeOffset(self, obj):
        GP = obj.data
        buffer = common.encodeString(GP.name_full)

        for modifier in obj.grease_pencil_modifiers:
            if modifier.type != 'GP_TIME':
                continue
            offset = modifier.offset
            scale = modifier.frame_scale
            customRange = modifier.use_custom_frame_range
            frameStart = modifier.frame_start
            frameEnd = modifier.frame_end
            buffer += common.encodeInt(offset) + common.encodeFloat(scale) + common.encodeBool(
                customRange) + common.encodeInt(frameStart) + common.encodeInt(frameEnd)
            self.addCommand(common.Command(
                common.MessageType.GREASE_PENCIL_TIME_OFFSET, buffer, 0))
            break

    def sendGreasePencilMesh(self, obj):
        GP = obj.data
        buffer = common.encodeString(GP.name_full)

        buffer += common.encodeInt(len(GP.materials))
        for material in GP.materials:
            if not material:
                materialName = "Default"
            else:
                materialName = material.name_full
            buffer += common.encodeString(materialName)

        buffer += common.encodeInt(len(GP.layers))
        for name, layer in GP.layers.items():
            buffer += self.sendGreasePencilLayer(layer, name)

        self.addCommand(common.Command(
            common.MessageType.GREASE_PENCIL_MESH, buffer, 0))

        self.sendGreasePencilTimeOffset(obj)

    def sendGreasePencilMaterial(self, material):
        GPMaterial = material.grease_pencil
        strokeEnable = GPMaterial.show_stroke
        strokeMode = GPMaterial.mode
        strokeStyle = GPMaterial.stroke_style
        strokeColor = GPMaterial.color
        strokeOverlap = GPMaterial.use_overlap_strokes
        fillEnable = GPMaterial.show_fill
        fillStyle = GPMaterial.fill_style
        fillColor = GPMaterial.fill_color
        GPMaterialBuffer = common.encodeString(material.name_full)
        GPMaterialBuffer += common.encodeBool(strokeEnable)
        GPMaterialBuffer += common.encodeString(strokeMode)
        GPMaterialBuffer += common.encodeString(strokeStyle)
        GPMaterialBuffer += common.encodeColor(strokeColor)
        GPMaterialBuffer += common.encodeBool(strokeOverlap)
        GPMaterialBuffer += common.encodeBool(fillEnable)
        GPMaterialBuffer += common.encodeString(fillStyle)
        GPMaterialBuffer += common.encodeColor(fillColor)
        self.addCommand(common.Command(
            common.MessageType.GREASE_PENCIL_MATERIAL, GPMaterialBuffer, 0))

    def sendGreasePencilConnection(self, obj):
        buffer = common.encodeString(self.getObjectPath(obj))
        buffer += common.encodeString(obj.data.name_full)
        self.addCommand(common.Command(
            common.MessageType.GREASE_PENCIL_CONNECTION, buffer, 0))

    def buildGreasePencilConnection(self, data):
        path, start = common.decodeString(data, 0)
        greasePencilName, start = common.decodeString(data, start)
        gp = shareData.blenderGreasePencils[greasePencilName]
        self.getOrCreateObjectData(path, gp)

    def decodeGreasePencilStroke(self, greasePencilFrame, strokeIndex, data, index):
        materialIndex, index = common.decodeInt(data, index)
        lineWidth, index = common.decodeInt(data, index)
        points, index = common.decodeArray(data, index, '5f', 5*4)

        if strokeIndex >= len(greasePencilFrame.strokes):
            stroke = greasePencilFrame.strokes.new()
        else:
            stroke = greasePencilFrame.strokes[strokeIndex]

        stroke.material_index = materialIndex
        stroke.line_width = lineWidth

        p = stroke.points
        if len(points) > len(p):
            p.add(len(points) - len(p))
        if len(points) < len(p):
            maxIndex = len(points) - 1
            for i in range(maxIndex, len(p)):
                p.pop(maxIndex)

        for i in range(len(p)):
            point = points[i]
            p[i].co = ((point[0], point[1], point[2]))
            p[i].pressure = point[3]
            p[i].strength = point[4]
        return index

    def decodeGreasePencilFrame(self, greasePencilLayer, data, index):
        greasePencilFrame, index = common.decodeInt(data, index)
        frame = None
        for f in greasePencilLayer.frames:
            if f.frame_number == greasePencilFrame:
                frame = f
                break
        if not frame:
            frame = greasePencilLayer.frames.new(greasePencilFrame)
        strokeCount, index = common.decodeInt(data, index)
        for strokeIndex in range(strokeCount):
            index = self.decodeGreasePencilStroke(
                frame, strokeIndex, data, index)
        return index

    def decodeGreasePencilLayer(self, greasePencil, data, index):
        greasePencilLayerName, index = common.decodeString(data, index)
        layer = greasePencil.get(greasePencilLayerName)
        if not layer:
            layer = greasePencil.layers.new(greasePencilLayerName)
        layer.hide, index = common.decodeBool(data, index)
        frameCount, index = common.decodeInt(data, index)
        for _ in range(frameCount):
            index = self.decodeGreasePencilFrame(layer, data, index)
        return index

    def buildGreasePencilMesh(self, data):
        greasePencilName, index = common.decodeString(data, 0)

        greasePencil = shareData.blenderGreasePencils.get(greasePencilName)
        if not greasePencil:
            greasePencil = bpy.data.grease_pencils.new(greasePencilName)
            shareData._blenderGreasePencils[greasePencil.name_full] = greasePencil

        greasePencil.materials.clear()
        materialCount, index = common.decodeInt(data, index)
        for _ in range(materialCount):
            materialName, index = common.decodeString(data, index)
            material = shareData.blenderMaterials.get(materialName)
            greasePencil.materials.append(material)

        layerCount, index = common.decodeInt(data, index)
        for _ in range(layerCount):
            index = self.decodeGreasePencilLayer(greasePencil, data, index)

    def buildGreasePencilMaterial(self, data):
        greasePencilMaterialName, start = common.decodeString(data, 0)
        material = shareData.blenderMaterials.get(greasePencilMaterialName)
        if not material:
            material = bpy.data.materials.new(greasePencilMaterialName)
            shareData._blenderMaterials[material.name_full] = material
        if not material.grease_pencil:
            bpy.data.materials.create_gpencil_data(material)

        GPMaterial = material.grease_pencil
        GPMaterial.show_stroke, start = common.decodeBool(data, start)
        GPMaterial.mode, start = common.decodeString(data, start)
        GPMaterial.stroke_style, start = common.decodeString(data, start)
        GPMaterial.color, start = common.decodeColor(data, start)
        GPMaterial.use_overlap_strokes, start = common.decodeBool(data, start)
        GPMaterial.show_fill, start = common.decodeBool(data, start)
        GPMaterial.fill_style, start = common.decodeString(data, start)
        GPMaterial.fill_color, start = common.decodeColor(data, start)

    def buildGreasePencil(self, data):
        objectPath, start = common.decodeString(data, 0)
        greasePencilName, start = common.decodeString(data, start)
        greasePencil = shareData.blenderGreasePencils.get(greasePencilName)
        if not greasePencil:
            greasePencil = bpy.data.grease_pencils.new(greasePencilName)
            self.getOrCreateObjectData(objectPath, greasePencil)

    def getDeleteBuffer(self, name):
        encodedName = name.encode()
        buffer = common.intToBytes(len(encodedName), 4) + encodedName
        return buffer

    def sendDelete(self, objName):
        self.addCommand(common.Command(
            common.MessageType.DELETE, self.getDeleteBuffer(objName), 0))

    def sendListRooms(self):
        self.addCommand(common.Command(common.MessageType.LIST_ROOMS))

    def on_connection_lost(self):
        bpy.ops.dcc_sync.disconnect()

    def buildListAllClients(self, client_ids):
        shareData.client_ids = client_ids
        ui.update_ui_lists()

    def sendSceneContent(self):
        if 'SendContent' in self.callbacks:
            self.callbacks['SendContent']()

    def sendFrame(self, frame):
        self.addCommand(common.Command(
            common.MessageType.FRAME, common.encodeInt(frame), 0))

    def sendFrameStartEnd(self, start, end):
        self.addCommand(common.Command(common.MessageType.FRAME_START_END,
                                       common.encodeInt(start) + common.encodeInt(end), 0))

    def clearContent(self):
        if 'ClearContent' in self.callbacks:
            self.callbacks['ClearContent']()

    def networkConsumer(self):
        self.fetchCommands()

        setDirty = True
        while True:
            command = self.getNextReceivedCommand()
            if command is None:
                break

            processed = False
            if command.type == common.MessageType.LIST_ALL_CLIENTS:
                clients, _ = common.decodeJson(command.data, 0)
                self.buildListAllClients(clients)
                processed = True
            elif command.type == common.MessageType.CONNECTION_LOST:
                self.on_connection_lost()
                break

            if setDirty:
                shareData.setDirty()
                setDirty = False

            self.blockSignals = True
            self.receivedCommandsProcessed = True
            if processed:
                # this was a room protocol command that was processed
                self.receivedCommandsProcessed = False
            else:
                if command.type == common.MessageType.CONTENT:
                    # The server asks for scene content (at room creation)
                    self.receivedCommandsProcessed = False
                    self.sendSceneContent()

                elif command.type == common.MessageType.GREASE_PENCIL_MESH:
                    self.buildGreasePencilMesh(command.data)
                elif command.type == common.MessageType.GREASE_PENCIL_MATERIAL:
                    self.buildGreasePencilMaterial(command.data)
                elif command.type == common.MessageType.GREASE_PENCIL_CONNECTION:
                    self.buildGreasePencilConnection(command.data)

                elif command.type == common.MessageType.CLEAR_CONTENT:
                    self.clearContent()
                elif command.type == common.MessageType.MESH:
                    self.buildMesh(command.data)
                elif command.type == common.MessageType.TRANSFORM:
                    self.buildTransform(command.data)
                elif command.type == common.MessageType.MATERIAL:
                    self.buildMaterial(command.data)
                elif command.type == common.MessageType.DELETE:
                    self.buildDelete(command.data)
                elif command.type == common.MessageType.CAMERA:
                    self.buildCamera(command.data)
                elif command.type == common.MessageType.LIGHT:
                    self.buildLight(command.data)
                elif command.type == common.MessageType.RENAME:
                    self.buildRename(command.data)
                elif command.type == common.MessageType.DUPLICATE:
                    self.buildDuplicate(command.data)
                elif command.type == common.MessageType.SEND_TO_TRASH:
                    self.buildSendToTrash(command.data)
                elif command.type == common.MessageType.RESTORE_FROM_TRASH:
                    self.buildRestoreFromTrash(command.data)
                elif command.type == common.MessageType.TEXTURE:
                    self.buildTextureFile(command.data)

                elif command.type == common.MessageType.COLLECTION:
                    collection_api.buildCollection(command.data)
                elif command.type == common.MessageType.COLLECTION_REMOVED:
                    collection_api.buildCollectionRemoved(command.data)

                elif command.type == common.MessageType.INSTANCE_COLLECTION:
                    collection_api. buildCollectionInstance(command.data)

                elif command.type == common.MessageType.ADD_COLLECTION_TO_COLLECTION:
                    collection_api.buildCollectionToCollection(command.data)
                elif command.type == common.MessageType.REMOVE_COLLECTION_FROM_COLLECTION:
                    collection_api.buildRemoveCollectionFromCollection(command.data)
                elif command.type == common.MessageType.ADD_OBJECT_TO_COLLECTION:
                    collection_api.buildAddObjectToCollection(command.data)
                elif command.type == common.MessageType.REMOVE_OBJECT_FROM_COLLECTION:
                    collection_api.buildRemoveObjectFromCollection(command.data)

                elif command.type == common.MessageType.ADD_COLLECTION_TO_SCENE:
                    scene_api.buildCollectionToScene(command.data)
                elif command.type == common.MessageType.REMOVE_COLLECTION_FROM_SCENE:
                    scene_api.buildRemoveCollectionFromScene(command.data)
                elif command.type == common.MessageType.ADD_OBJECT_TO_SCENE:
                    scene_api.buildAddObjectToScene(command.data)
                elif command.type == common.MessageType.REMOVE_OBJECT_FROM_SCENE:
                    scene_api.buildRemoveObjectFromScene(command.data)

                elif command.type == common.MessageType.SCENE:
                    scene_api.buildScene(command.data)
                elif command.type == common.MessageType.SCENE_REMOVED:
                    scene_api.buildSceneRemoved(command.data)

                self.receivedCommands.task_done()
                self.blockSignals = False

        if not setDirty:
            shareData.updateCurrentData()

        if len(shareData.pendingParenting) > 0:
            remainingParentings = set()
            for path in shareData.pendingParenting:
                pathElem = path.split('/')
                ob = None
                parent = None
                for elem in pathElem:
                    ob = shareData.blenderObjects.get(elem)
                    if not ob:
                        remainingParentings.add(path)
                        break
                    if ob.parent != parent:  # do it only if needed, otherwise it resets matrix_parent_inverse
                        ob.parent = parent
                    parent = ob
            shareData.pendingParenting = remainingParentings

        return 0.01
