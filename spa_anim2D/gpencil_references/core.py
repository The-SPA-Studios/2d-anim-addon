# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy
import bpy_extras
from mathutils import Vector


# Maps the values for `bpy.types.GPencilSculptSettings.lock_axis` to `bpy.ops.gpencil.reproject.type`
reprojection_type_map = {
    "VIEW": "VIEW",
    "AXIS_Y": "FRONT",
    "AXIS_X": "SIDE",
    "AXIS_Z": "TOP",
    "CURSOR": "CURSOR",
}


def calculate_view_center_location(obj: bpy.types.Object, region: bpy.types.Region):
    rv3d: bpy.types.RegionView3D = region.data
    obj_loc = obj.matrix_world.to_translation().to_3d()
    center_coords = (region.width / 2, region.height / 2)
    return bpy_extras.view3d_utils.region_2d_to_location_3d(
        region, rv3d, center_coords, obj_loc
    )


def calculate_camera_border_height_pixels(scene, camera_obj, region, rv3d):
    points = camera_obj.data.view_frame(scene=scene)[:2]
    points = [camera_obj.matrix_world @ v for v in points]
    points_px = [
        bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, v)
        for v in points
    ]
    return (points_px[0] - points_px[1]).length


def calculate_image_width_world_space(region, rv3d, obj_loc, width):
    p_start = bpy_extras.view3d_utils.region_2d_to_location_3d(
        region, rv3d, (0, 0), obj_loc
    )
    p_end = bpy_extras.view3d_utils.region_2d_to_location_3d(
        region, rv3d, (width, 0), obj_loc
    )
    p_vec = p_end - p_start

    return p_vec.length


def create_gpencil_reference(
    gpd: bpy.types.GreasePencil,
    gpf: bpy.types.GPencilFrame,
    image: bpy.types.Image,
    width: float,
    height: float,
    location: Vector,
) -> bpy.types.GPencilStroke:
    """
    Add a rectangular stroke textured with `image` to the given grease pencil fame.

    :param gpd: The grease pencil data.
    :param gpf: The grease pencil frame.
    :param image: The image to use as texture.
    :param width: The width of the rectangle.
    :param height: The height of the rectangle.
    :param location: The location of the rectangle.
    :return: The created grease pencil stroke.
    """
    name = image.name

    # Create new material
    mat = bpy.data.materials.new(f".ref/{name}")
    bpy.data.materials.create_gpencil_data(mat)
    gpd.materials.append(mat)
    idx = gpd.materials.find(mat.name)

    # Setup material settings
    mat.grease_pencil.show_stroke = False
    mat.grease_pencil.show_fill = True
    mat.grease_pencil.fill_image = image
    mat.grease_pencil.fill_style = "TEXTURE"
    mat.grease_pencil.mix_factor = 0.0
    mat.grease_pencil.texture_offset = (0.0, 0.0)
    mat.grease_pencil.texture_angle = 0.0
    mat.grease_pencil.texture_scale = (1.0, 1.0)
    mat.grease_pencil.texture_clamp = True

    # Create the stroke
    gps_new = gpf.strokes.new()
    gps_new.points.add(4, pressure=0, strength=0)
    # This will make sure that the uv's always remain the same
    gps_new.use_automatic_uvs = False
    gps_new.use_cyclic = True
    gps_new.material_index = idx

    # TODO: Align the stroke with the drawing plane
    coords = [
        location + Vector(c)
        for c in (
            (width / 2, 0, height / 2),
            (-width / 2, 0, height / 2),
            (-width / 2, 0, -height / 2),
            (width / 2, 0, -height / 2),
        )
    ]
    uvs = [(0.5, 0.5), (-0.5, 0.5), (-0.5, -0.5), (0.5, -0.5)]

    for i, (co, uv) in enumerate(zip(coords, uvs)):
        gps_new.points[i].co = co
        gps_new.points[i].uv_fill = uv

    return gps_new


def import_image_as_gp_reference(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    img_filepath: str,
    pack_image: bool,
    add_new_layer: bool,
    add_new_keyframe: bool,
):
    """
    Import image from `img_filepath` as a textured rectangle in the given
    grease pencil object.

    :param context: The active context.
    :param obj: The grease pencil object.
    :param filepath: The image filepath
    :param pack_image: Whether to pack the image into the Blender file.
    :param add_new_layer: Whether to add a new layer.
    """
    scene = context.scene
    rv3d = context.region.data
    gpd: bpy.types.GreasePencil = obj.data
    ts = context.tool_settings
    center = calculate_view_center_location(obj, context.region)

    image = bpy.data.images.load(img_filepath)
    if pack_image:
        image.pack()

    if not gpd.layers.active:
        gpl = gpd.layers.new(image.name)
    else:
        if add_new_layer:
            gpl = gpd.layers.new(image.name)
        else:
            gpl = gpd.layers.active

    if not gpl.active_frame:
        gpf = gpl.frames.new(context.scene.frame_current)
    else:
        if (
            ts.use_keyframe_insert_auto or add_new_keyframe
        ) and gpl.active_frame.frame_number != context.scene.frame_current:
            gpf = gpl.frames.new(context.scene.frame_current)
        else:
            gpf = gpl.active_frame

    if rv3d.view_perspective == "CAMERA":
        h = calculate_camera_border_height_pixels(
            scene, scene.camera, context.region, rv3d
        )
    else:
        h = context.region.height - 100  # margin of 50 pxS

    aspect = image.size[0] / image.size[1]
    image_width = calculate_image_width_world_space(
        context.region,
        context.region.data,
        center,
        h * aspect,
    )
    image_height = image_width / aspect

    gps: bpy.types.GPencilStroke = create_gpencil_reference(
        gpd,
        gpf,
        image,
        image_width,
        image_height,
        center,
    )

    # Selection
    bpy.ops.gpencil.select_all(action="DESELECT")
    gps.select = True

    # Reproject the reference flat to the drawing plane
    bpy.ops.gpencil.reproject(type=reprojection_type_map[ts.gpencil_sculpt.lock_axis])
