# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import math
import bpy

# FIXME: https://developer.blender.org/T100203
#        Use getter and setter function instead of "camera_view_depth" property until
#        fixed.
from spa_anim2D.layout.core import (
    camera_view_depth_set,
    camera_view_depth_get,
    set_depth_from_camera,
)


def test_camera_view_depth_set():
    ob = bpy.context.active_object
    camera_view_depth_set(ob, 10)
    # Ensure camera_view_depth computation is returning the correct value.
    assert camera_view_depth_get(ob) == 10


def test_camera_view_depth_scale_adjustment():
    ob = bpy.context.active_object
    sc = ob.scale.copy()
    # Multiplying the depth by 2 should multiply the scale by 2.
    depth = camera_view_depth_get(ob)
    camera_view_depth_set(ob, depth * 2)
    assert ob.scale == sc * 2


def test_camera_view_depth_no_scale_adjustment():
    ob = bpy.context.active_object
    sc = ob.scale.copy()
    depth = 10
    # Set object's depth without ajdusting scale.
    set_depth_from_camera(
        bpy.context.scene.camera.matrix_world, ob, depth, adjust_scale=False
    )
    # Scale should be unchanged with depth should have been updated.
    assert ob.scale == sc
    assert camera_view_depth_get(ob) == depth


def test_camera_view_depth_no_active_cam():
    ob = bpy.context.active_object
    # Unset active camera.
    bpy.context.scene.camera = None
    # Ensure camera_view_depth is returning NaN.
    assert math.isnan(camera_view_depth_get(ob))
    # This should still work, but be a no-op.
    camera_view_depth_set(ob, 10)
    assert math.isnan(camera_view_depth_get(ob))
