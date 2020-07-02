from enum import IntEnum

import bpy
from mixer.share_data import share_data
from mixer.shot_manager_data import Shot

import mixer.broadcaster.common as common


class SMAction(IntEnum):
    ADD_SHOT = 0
    DELETE_SHOT = 1
    DUPLICATE_SHOT = 2
    MOVE_SHOT = 3
    UPDATE_SHOT = 4


def build_shot_manager_action(data):
    index = 0
    action, index = common.decode_int(data, index)
    shot_index, index = common.decode_int(data, index)
    # bpy.context.scene.UAS_shot_manager_props.selected_shot_index = shot_index
    bpy.context.scene.UAS_shot_manager_props.setSelectedShotByIndex(shot_index)

    # Add
    if action == SMAction.ADD_SHOT:
        shot_name, index = common.decode_string(data, index)
        start, index = common.decode_int(data, index)
        end, index = common.decode_int(data, index)
        camera, index = common.decode_string(data, index)
        color, index = common.decode_color(data, index)
        if len(camera) == 0:
            camera = bpy.data.cameras[0].name_full
        bpy.context.scene.UAS_shot_manager_props.get_isInitialized()
        bpy.ops.uas_shot_manager.add_shot(
            name=shot_name, start=start, end=end, cameraName=camera, color=(color[0], color[1], color[2])
        )
    # Delete
    elif action == SMAction.DELETE_SHOT:
        bpy.ops.uas_shot_manager.remove_shot()
    # Duplicate
    elif action == SMAction.DUPLICATE_SHOT:
        shot_name, index = common.decode_string(data, index)
        bpy.ops.uas_shot_manager.duplicate_shot(name=shot_name)  # duplicate name
    # Move
    elif action == SMAction.MOVE_SHOT:
        offset, index = common.decode_int(data, index)
        bpy.ops.uas_shot_manager.list_action(action="DOWN" if offset > 0 else "UP")
    # Update
    elif action == SMAction.UPDATE_SHOT:
        take = bpy.context.scene.UAS_shot_manager_props.current_take_name
        start, index = common.decode_int(data, index)
        end, index = common.decode_int(data, index)
        camera, index = common.decode_string(data, index)
        color, index = common.decode_color(data, index)
        enabled, index = common.decode_int(data, index)
        if start > -1:
            bpy.context.scene.UAS_shot_manager_props.takes[take].shots[shot_index].start = start
        if end > -1:
            bpy.context.scene.UAS_shot_manager_props.takes[take].shots[shot_index].end = end
        if len(camera) > 0:
            bpy.context.scene.UAS_shot_manager_props.takes[take].shots[shot_index].camera = bpy.data.objects[camera]
        if color[0] > -1:
            bpy.context.scene.UAS_shot_manager_props.takes[take].shots[shot_index].color = color
        if enabled != -1:
            bpy.context.scene.UAS_shot_manager_props.takes[take].shots[shot_index].enabled = enabled


def send_montage_mode():
    buffer = common.encode_bool(share_data.shot_manager.montage_mode)
    share_data.client.add_command(common.Command(common.MessageType.SHOT_MANAGER_MONTAGE_MODE, buffer, 0))


def check_montage_mode():
    winman = bpy.data.window_managers["WinMan"]
    if not hasattr(winman, "UAS_shot_manager_handler_toggle"):
        return False

    montage_mode = winman.UAS_shot_manager_handler_toggle
    if share_data.shot_manager.montage_mode is None or montage_mode != share_data.shot_manager.montage_mode:
        share_data.shot_manager.montage_mode = montage_mode
        send_montage_mode()
        return True
    return False


def send_frame():
    if not hasattr(bpy.context.scene, "UAS_shot_manager_props"):
        return

    shot_manager = bpy.context.scene.UAS_shot_manager_props
    if share_data.shot_manager.current_shot_index != shot_manager.current_shot_index:
        share_data.shot_manager.current_shot_index = shot_manager.current_shot_index
        buffer = common.encode_int(share_data.shot_manager.current_shot_index)
        share_data.client.add_command(common.Command(common.MessageType.SHOT_MANAGER_CURRENT_SHOT, buffer, 0))


def get_state():
    if not hasattr(bpy.context.scene, "UAS_shot_manager_props"):
        return

    shot_manager = bpy.context.scene.UAS_shot_manager_props
    if shot_manager is None:
        return

    share_data.shot_manager.current_take_name = shot_manager.current_take_name
    if not share_data.shot_manager.current_take_name or share_data.shot_manager.current_take_name == "":
        return

    share_data.shot_manager.shots = []
    for shot in shot_manager.takes[shot_manager.current_take_name].shots:
        new_shot = Shot()
        new_shot.name = shot.name
        if shot.camera:
            new_shot.camera_name = shot.camera.name_full
        new_shot.start = shot.start
        new_shot.end = shot.end
        new_shot.enabled = shot.enabled
        share_data.shot_manager.shots.append(new_shot)


def send_scene():
    get_state()
    buffer = common.encode_int(len(share_data.shot_manager.shots))
    for shot in share_data.shot_manager.shots:
        buffer += (
            common.encode_string(shot.name)
            + common.encode_string(shot.camera_name)
            + common.encode_int(shot.start)
            + common.encode_int(shot.end)
            + common.encode_bool(shot.enabled)
        )
    share_data.client.add_command(common.Command(common.MessageType.SHOT_MANAGER_CONTENT, buffer, 0))


def update_scene():
    if not hasattr(bpy.context.scene, "UAS_shot_manager_props"):
        return

    shot_manager = bpy.context.scene.UAS_shot_manager_props
    if shot_manager is None:
        return

    current_take_name = shot_manager.current_take_name
    if current_take_name is None or current_take_name == "":
        return

    if current_take_name != share_data.shot_manager.current_take_name:
        send_scene()
        return

    take = shot_manager.takes[current_take_name]
    shots = take.shots
    if len(shots) != len(share_data.shot_manager.shots):
        send_scene()
        return

    for i, shot in enumerate(shots):
        prev_shot = share_data.shot_manager.shots[i]
        camera_name = ""
        if shot.camera:
            camera_name = shot.camera.name_full
        if (
            prev_shot.name != shot.name
            or prev_shot.camera_name != camera_name
            or prev_shot.start != shot.start
            or prev_shot.end != shot.end
            or prev_shot.enabled != shot.enabled
        ):
            send_scene()
            return
