# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import pytest

import bpy
import bisect

from spa_anim2D.animation.core import (
    shift_gp_keyframes,
    gp_compute_list_of_frames_to_duplicate,
)


@pytest.fixture()
def gp_object() -> bpy.types.Object:
    # Setup a Grease Pencil object with some (empty) keyframes
    bpy.ops.object.gpencil_add(type="EMPTY")
    gp_object = bpy.context.active_object
    gp_object.data.clear()
    gp_object.data.layers.new(name="TestLayer", set_active=True)
    return gp_object


@pytest.fixture()
def keyframed_gp_A(gp_object) -> tuple[bpy.types.Object, list[int]]:
    keyframes = [3, 4, 5, 7, 9, 12]
    for keyframe in keyframes:
        gp_object.data.layers.active.frames.new(keyframe)

    return gp_object, keyframes


def test_shift_gp_keyframes_positive_offset(keyframed_gp_A):
    gp_object, base_keyframes = keyframed_gp_A
    gp_layer = gp_object.data.layers.active

    # Setup parameters
    frame_start = 5
    offset = 1

    # Shift keyframes
    shift_gp_keyframes(gp_object.data, frame_start, offset)

    split_idx = bisect.bisect(base_keyframes, frame_start)
    pre_keys, post_keys = gp_layer.frames[:split_idx], gp_layer.frames[split_idx:]
    # Keyframes <= frame_start shouldn't have changed
    assert [f.frame_number for f in pre_keys] == base_keyframes[:split_idx]
    # Keyframes > frame_start should have been shifted
    assert [f.frame_number - offset for f in post_keys] == base_keyframes[split_idx:]


def test_shift_gp_keyframes_non_applicable_negative_offset(keyframed_gp_A):
    gp_object, base_keyframes = keyframed_gp_A
    gp_layer = gp_object.data.layers.active

    # Setup parameters
    frame_start = 4
    offset = -10

    # Shift keyframes
    keys = shift_gp_keyframes(gp_object.data, frame_start, offset)

    # Offset is not applicable, no keys should have been impacted
    assert not keys
    assert [f.frame_number for f in gp_layer.frames] == base_keyframes


def test_shift_gp_keyframes_active_layer_only(keyframed_gp_A):
    gp_object, base_keyframes = keyframed_gp_A
    gp_layer = gp_object.data.layers.active

    # Create a new layer by duplicating the active layer
    bpy.ops.gpencil.layer_duplicate()
    active_layer = gp_object.data.layers.active

    # This offsets all the keys
    frame_start = 0
    offset = 1

    # Shift keyframes
    keys = shift_gp_keyframes(
        gp_object.data, frame_start, offset, only_active_layer=True
    )

    # Only frames on the active layer should have changed
    assert len(keys) == len(active_layer.frames)
    assert [f.frame_number for f in gp_layer.frames] == base_keyframes
    assert [f.frame_number - offset for f in active_layer.frames] == base_keyframes


def test_shift_gp_keyframes_unlocked_layers_only(keyframed_gp_A):
    gp_object, base_keyframes = keyframed_gp_A
    gp_layer = gp_object.data.layers.active

    # Create a new layer by duplicating the active layer, and lock it
    bpy.ops.gpencil.layer_duplicate()
    locked_layer = gp_object.data.layers.active
    locked_layer.lock = True

    # This offsets all the keys in the GP object
    frame_start = 0
    offset = 1

    # Shift keyframes
    keys = shift_gp_keyframes(
        gp_object.data, frame_start, offset, only_unlocked_layers=True
    )

    # Only frames on the unlocked layer should have changed
    assert len(keys) == len(gp_layer.frames)
    assert [f.frame_number for f in locked_layer.frames] == base_keyframes
    assert [f.frame_number - offset for f in gp_layer.frames] == base_keyframes


def test_shift_gp_keyframes_active_and_unlocked_layers_only(keyframed_gp_A):
    gp_object, base_keyframes = keyframed_gp_A
    gp_layer = gp_object.data.layers.active

    # Create a new layer by duplicating the active layer, and lock it
    bpy.ops.gpencil.layer_duplicate()
    locked_layer = gp_object.data.layers.active
    locked_layer.lock = True

    # This offsets all the keys in the GP object
    frame_start = 0
    offset = 1

    # Shift keyframes
    keys = shift_gp_keyframes(
        gp_object.data,
        frame_start,
        offset,
        only_active_layer=True,
        only_unlocked_layers=True,
    )

    # This combination of settings should not change anything: the active layer is locked
    assert not keys
    assert [f.frame_number for f in locked_layer.frames] == base_keyframes
    assert [f.frame_number for f in gp_layer.frames] == base_keyframes


def test_gp_create_new_duplicated_frames_no_keyframes(gp_object):
    gpl = gp_object.data.layers[0]
    frame_numbers = [1, 2, 3]
    frames_to_duplicate = gp_compute_list_of_frames_to_duplicate(gpl, frame_numbers)

    # No frames are created because there are no frames to be duplicated.
    assert len(frames_to_duplicate) == 0


def test_gp_create_new_duplicated_frames_simple(gp_object):
    gpl: bpy.types.GPencilLayer = gp_object.data.layers[0]
    gpf0 = gpl.frames.new(0)

    frame_numbers = [1, 2, 3]
    frames_to_duplicate = gp_compute_list_of_frames_to_duplicate(gpl, frame_numbers)

    # Three new frames are created and they are all duplicates of the first frame.
    assert len(frames_to_duplicate) == 3
    assert [(gpf, frame_number) for gpf, frame_number in frames_to_duplicate] == [
        (gpf0, 1),
        (gpf0, 2),
        (gpf0, 3),
    ]


def test_gp_create_new_duplicated_frames_duplicate(gp_object):
    gpl: bpy.types.GPencilLayer = gp_object.data.layers[0]
    gpf0 = gpl.frames.new(0)
    gpl.frames.new(3)

    frame_numbers = [1, 2, 3]
    frames_to_duplicate = gp_compute_list_of_frames_to_duplicate(gpl, frame_numbers)

    # Two new frames are created (the keyframe on frame 3 is not duplicated).
    assert len(frames_to_duplicate) == 2
    assert [(gpf, frame_number) for gpf, frame_number in frames_to_duplicate] == [
        (gpf0, 1),
        (gpf0, 2),
    ]


def test_gp_create_new_duplicated_frames_before_first(gp_object):
    gpl: bpy.types.GPencilLayer = gp_object.data.layers[0]
    gpf3 = gpl.frames.new(3)

    frame_numbers = [1, 2, 3, 4]
    frames_to_duplicate = gp_compute_list_of_frames_to_duplicate(gpl, frame_numbers)

    # Only one frame is duplicated. All the frames before frame 3 cannot be duplicated.
    assert len(frames_to_duplicate) == 1
    assert [(gpf, frame_number) for gpf, frame_number in frames_to_duplicate] == [
        (gpf3, 4),
    ]


def test_gp_create_new_duplicated_frames_complicated(gp_object):
    gpl: bpy.types.GPencilLayer = gp_object.data.layers[0]
    gpf3 = gpl.frames.new(3)
    gpf6 = gpl.frames.new(6)

    frame_numbers = [1, 2, 4, 5, 6, 7]
    frames_to_duplicate = gp_compute_list_of_frames_to_duplicate(gpl, frame_numbers)

    assert len(frames_to_duplicate) == 3
    assert [(gpf, frame_number) for gpf, frame_number in frames_to_duplicate] == [
        (gpf3, 4),
        (gpf3, 5),
        (gpf6, 7),
    ]
