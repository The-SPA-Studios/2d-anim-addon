# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import sys
import math
import mathutils

import bpy
import bpy_extras


def get_pixel_size_at_location(
    context: bpy.types.Context, loc: mathutils.Vector
) -> float:
    """Get pixel size at given 3D location.

    :param context: The active context.
    :param location: The 3d location to get pixel size at.
    :returns: The size of a screen pixel at given location.
    """
    rv3d = context.space_data.region_3d
    p_start = bpy_extras.view3d_utils.region_2d_to_location_3d(
        context.region, rv3d, (0, 0), loc
    )
    p_end = bpy_extras.view3d_utils.region_2d_to_location_3d(
        context.region, rv3d, (0, 1), loc
    )
    return (p_end - p_start).length


def get_pixel_size_at_object_location(
    context: bpy.types.Context, obj: bpy.types.Object
) -> float:
    """Get pixel width at `obj` location.

    :param context: The active context.
    :param obj: The object to consider.
    :returns: The size of a screen pixel at object location.
    """
    return get_pixel_size_at_location(context, obj.matrix_world.translation.to_3d())


def get_depth_from_view(view_matrix: mathutils.Matrix, obj: bpy.types.Object):
    """Get depth of `obj` from `view matrix`."""
    return -(view_matrix @ obj.matrix_world).translation.z


def set_depth_from_camera(
    cam_matrix: mathutils.Matrix,
    obj: bpy.types.Object,
    depth: float,
    adjust_scale: bool = False,
):
    """Place `obj` at given `depth` from camera, in camera-to-object axis.

    :param cam_matrix: The camera world matrix.
    :param obj: The object to move in space.
    :param depth: The depth to place the object at.
    :param adjust_scale: Whether to scale to object to compensate for the translation.
    """
    # Don't transform object with location or scale locked.
    if any(obj.lock_scale[:] + obj.lock_location[:]):
        return

    view_matrix = cam_matrix.inverted()
    view_loc = cam_matrix.translation.to_3d()
    current_depth = get_depth_from_view(view_matrix, obj)

    # If object is at camera location, add an initial offset.
    if abs(current_depth) < sys.float_info.epsilon:
        current_depth = 1
        cam_to_obj_vec = cam_matrix @ mathutils.Vector((0, 0, -current_depth))
    else:
        cam_to_obj_vec = obj.matrix_world.translation.to_3d() - view_loc

    depth_diff_ratio = depth / current_depth

    # Build transformation matrix to scale from camera center.
    scale_mat = mathutils.Matrix.Scale(depth_diff_ratio, 4)
    trans_cam = mathutils.Matrix.Translation(cam_to_obj_vec)
    transform_mat = trans_cam.inverted() @ scale_mat @ trans_cam

    # Decompose object matrix in:
    ob_loc, ob_rot, ob_sc = obj.matrix_world.decompose()
    #  - pre-matrix: scale & rotation
    pre_matrix = mathutils.Matrix.LocRotScale(mathutils.Vector(), ob_rot, ob_sc)
    #  - post-matrix: translation
    post_mat = mathutils.Matrix.Translation(ob_loc)

    # Compose the full transformation matrix.
    obj.matrix_world = post_mat @ transform_mat @ pre_matrix

    # Restore local scale if compensation is disabled.
    if not adjust_scale:
        obj.scale = ob_sc


def camera_view_depth_get(obj: bpy.types.Object) -> float:
    """Get `obj`'s depth from active camera."""
    if cam := bpy.context.scene.camera:
        return get_depth_from_view(cam.matrix_world.inverted(), obj)

    return math.nan


def camera_view_depth_set(obj: bpy.types.Object, value: float):
    """Set object depth from current camera in camera-to-object axis."""
    if (cam := bpy.context.scene.camera) and obj != cam:
        set_depth_from_camera(cam.matrix_world, obj, value, True)


def deselect_all(context: bpy.types.Context):
    """Deselect selected objects in active context."""
    for obj in context.selected_objects:
        obj.select_set(False)


def register():
    # Deactivate this feature for now, since it causes Blender to freeze when
    # using library overrides.
    # See: https://developer.blender.org/T100203

    # bpy.types.Object.camera_view_depth = bpy.props.FloatProperty(
    #     name="Depth from Active Camera View",
    #     get=camera_view_depth_get,
    #     set=camera_view_depth_set,
    #     subtype="DISTANCE",
    #     precision=3,
    #     step=10,
    #     unit="LENGTH",
    #     options=set(),
    # )
    pass


def unregister():
    # del bpy.types.Object.camera_view_depth
    pass
