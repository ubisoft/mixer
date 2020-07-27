from mixer.share_data import share_data
from mixer.bl_utils import get_mixer_prefs
from mixer.broadcaster.common import ClientMetadata

import bpy
from mathutils import Matrix, Vector

import logging

logger = logging.getLogger(__name__)


class DrawHandlers:
    users_frustums_draw_handler = None
    users_frustum_name_draw_handler = None
    users_selection_draw_handler = None
    users_selection_name_draw_handler = None


_draw_handlers = DrawHandlers()


def set_draw_handlers():
    global _draw_handlers

    if not _draw_handlers.users_frustums_draw_handler:
        _draw_handlers.users_frustums_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            users_frustrum_draw, (), "WINDOW", "POST_VIEW"
        )
    if not _draw_handlers.users_frustum_name_draw_handler:
        _draw_handlers.users_frustum_name_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            users_frustum_name_draw, (), "WINDOW", "POST_PIXEL"
        )
    if not _draw_handlers.users_selection_draw_handler:
        _draw_handlers.users_selection_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            users_selection_draw, (), "WINDOW", "POST_VIEW"
        )
    if not _draw_handlers.users_selection_name_draw_handler:
        _draw_handlers.users_selection_name_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            users_selection_name_draw, (), "WINDOW", "POST_PIXEL"
        )


def remove_draw_handlers():
    if _draw_handlers.users_frustums_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handlers.users_frustums_draw_handler, "WINDOW")
        _draw_handlers.users_frustums_draw_handler = None
    if _draw_handlers.users_frustum_name_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handlers.users_frustum_name_draw_handler, "WINDOW")
        _draw_handlers.users_frustum_name_draw_handler = None
    if _draw_handlers.users_selection_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handlers.users_selection_draw_handler, "WINDOW")
        _draw_handlers.users_selection_draw_handler = None
    if _draw_handlers.users_selection_name_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handlers.users_selection_name_draw_handler, "WINDOW")
        _draw_handlers.users_selection_name_draw_handler = None


def users_frustrum_draw():
    prefs = get_mixer_prefs()

    if not prefs.display_frustums_gizmos or share_data.current_room is None:
        return

    import bgl
    import gpu
    from gpu_extras.batch import batch_for_shader

    shader = gpu.shader.from_builtin("3D_UNIFORM_COLOR")
    shader.bind()

    bgl.glLineWidth(1.5)
    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)
    bgl.glPointSize(4)

    indices = ((1, 2), (2, 3), (3, 4), (4, 1), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5))

    def per_user_callback(user_dict):
        user_color = user_dict.get(ClientMetadata.USERCOLOR, DEFAULT_COLOR)
        shader.uniform_float("color", (*user_color, 1))
        return True

    def per_frustum_callback(user_dict, frustum):
        position = [tuple(coord) for coord in frustum]
        batch = batch_for_shader(shader, "LINES", {"pos": position}, indices=indices)
        batch.draw(shader)

        batch = batch_for_shader(shader, "POINTS", {"pos": position}, indices=(5,))
        batch.draw(shader)

    users_frustrum_draw_iteration(per_user_callback, per_frustum_callback)


def users_frustum_name_draw():
    prefs = get_mixer_prefs()

    if not prefs.display_names_gizmos or share_data.current_room is None:
        return

    def per_user_callback(user_dict):
        user_name = user_dict.get(ClientMetadata.USERNAME, None)
        return user_name is not None

    def per_frustum_callback(user_dict, frustum):
        draw_user_name(user_dict, frustum[0])

    users_frustrum_draw_iteration(per_user_callback, per_frustum_callback)


def users_frustrum_draw_iteration(per_user_callback, per_frustum_callback):
    if share_data.client_ids is None:
        return

    prefs = get_mixer_prefs()

    for user_dict in share_data.client_ids.values():
        scenes = user_dict.get(ClientMetadata.USERSCENES, None)
        if not scenes:
            continue

        user_id = user_dict[ClientMetadata.ID]
        user_room = user_dict[ClientMetadata.ROOM]
        if (
            not prefs.display_own_gizmos and share_data.client.client_id == user_id
        ) or share_data.current_room != user_room:
            continue  # don't draw my own frustums or frustums from users outside my room

        if not per_user_callback(user_dict):
            continue

        for scene_name, scene_dict in scenes.items():
            if scene_name != bpy.context.scene.name_full:
                continue

            views = scene_dict.get(ClientMetadata.USERSCENES_VIEWS, None)
            if views is None:
                continue

            for view_id, view_dict in views.items():
                if share_data.client.client_id == user_id and view_id == str(bpy.context.area.as_pointer()):
                    continue  # Only occurs when drawing my own frustum

                frustum = [
                    view_dict[ClientMetadata.USERSCENES_VIEWS_EYE],
                    *view_dict[ClientMetadata.USERSCENES_VIEWS_SCREEN_CORNERS],
                    view_dict[ClientMetadata.USERSCENES_VIEWS_TARGET],
                ]
                per_frustum_callback(user_dict, frustum)


def users_selection_draw():
    import bgl
    import gpu
    from gpu_extras.batch import batch_for_shader

    prefs = get_mixer_prefs()

    if not prefs.display_selections_gizmos or share_data.current_room is None:
        return

    shader = gpu.shader.from_builtin("3D_UNIFORM_COLOR")
    shader.bind()

    bgl.glLineWidth(1.5)
    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_LINE_SMOOTH)

    indices = ((0, 1), (1, 2), (2, 3), (0, 3), (4, 5), (5, 6), (6, 7), (4, 7), (0, 4), (1, 5), (2, 6), (3, 7))

    def per_user_callback(user_dict):
        user_color = user_dict.get(ClientMetadata.USERCOLOR, DEFAULT_COLOR)
        shader.uniform_float("color", (*user_color, 1))
        return True

    def per_object_callback(user_dict, object, matrix, local_bbox):
        bbox_corners = [matrix @ Vector(corner) for corner in local_bbox]

        batch = batch_for_shader(shader, "LINES", {"pos": bbox_corners}, indices=indices)
        batch.draw(shader)

    users_selection_draw_iteration(per_user_callback, per_object_callback)


def users_selection_name_draw():
    prefs = get_mixer_prefs()

    if not prefs.display_names_gizmos or share_data.current_room is None:
        return

    def per_user_callback(user_dict):
        user_name = user_dict.get(ClientMetadata.USERNAME, None)
        return user_name is not None

    def per_object_callback(user_dict, object, matrix, local_bbox):
        bbox_corner = matrix @ Vector(local_bbox[1])
        draw_user_name(user_dict, bbox_corner)

    users_selection_draw_iteration(per_user_callback, per_object_callback)


def users_selection_draw_iteration(per_user_callback, per_object_callback):
    if share_data.client_ids is None:
        return

    prefs = get_mixer_prefs()

    for user_dict in share_data.client_ids.values():
        scenes = user_dict.get(ClientMetadata.USERSCENES, None)
        if not scenes:
            continue

        user_id = user_dict[ClientMetadata.ID]
        user_room = user_dict[ClientMetadata.ROOM]
        if (
            not prefs.display_own_gizmos and share_data.client.client_id == user_id
        ) or share_data.current_room != user_room:
            continue  # don't draw my own selection or selection from users outside my room

        if not per_user_callback(user_dict):
            continue

        for scene_name, scene_dict in scenes.items():
            if scene_name != bpy.context.scene.name_full:
                continue

            selected_objects = scene_dict.get(ClientMetadata.USERSCENES_SELECTED_OBJECTS, None)
            if selected_objects is None:
                continue

            for object_full_name in selected_objects:
                if object_full_name not in bpy.data.objects:
                    logger.warning(f"{object_full_name} not in bpy.data")
                    continue

                obj = bpy.data.objects[object_full_name]
                objects = [obj]
                parent_matrix = IDENTITY_MATRIX

                if obj.type == "EMPTY" and obj.instance_collection is not None:
                    objects = obj.instance_collection.objects
                    parent_matrix = obj.matrix_world

                    per_object_callback(user_dict, obj, obj.matrix_world @ BBOX_SCALE_MATRIX, DEFAULT_BBOX)

                for obj in objects:
                    bbox = obj.bound_box

                    diag = Vector(bbox[2]) - Vector(bbox[4])
                    if diag.length_squared == 0:
                        bbox = DEFAULT_BBOX

                    per_object_callback(user_dict, obj, parent_matrix @ obj.matrix_world @ BBOX_SCALE_MATRIX, bbox)


def draw_user_name(user_dict, coord_3d):
    prefs = get_mixer_prefs()

    import blf
    from bpy_extras import view3d_utils

    text_coords = view3d_utils.location_3d_to_region_2d(bpy.context.region, bpy.context.region_data, tuple(coord_3d))
    if text_coords is None:
        return  # Sometimes happen, maybe due to mathematical precision issues or incoherencies
    blf.position(0, text_coords[0], text_coords[1] + 10, 0)
    blf.size(0, 16, 72)
    user_color = user_dict.get(ClientMetadata.USERCOLOR, DEFAULT_COLOR)
    blf.color(0, user_color[0], user_color[1], user_color[2], 1.0)

    text = user_dict.get(ClientMetadata.USERNAME, None)
    if prefs.display_ids_gizmos:
        text += f" ({user_dict[ClientMetadata.ID]})"

    blf.draw(0, text)


# Order of points returned by Blender's bound_box:
# -X -Y -Z
# -X -Y +Z
# -X +Y +Z
# -X +Y -Z
# +X -Y -Z
# +X -Y +Z
# +X +Y +Z
# +X +Y -Z
DEFAULT_BBOX = [
    (-1, -1, -1),
    (-1, -1, +1),
    (-1, +1, +1),
    (-1, +1, -1),
    (+1, -1, -1),
    (+1, -1, +1),
    (+1, +1, +1),
    (+1, +1, -1),
]

BBOX_SCALE_MATRIX = Matrix.Scale(1.05, 4)
IDENTITY_MATRIX = Matrix()

DEFAULT_COLOR = (1, 0, 1)
