# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

"""
Utility functions to manipulate dopesheet elements.
"""

from enum import Flag, auto
import sys
from typing import Optional

import bpy


keyframe_types = {
    "KEYFRAME": "HANDLETYPE_FREE_VEC",
    "EXTREME": "KEYTYPE_EXTREME_VEC",
    "BREAKDOWN": "KEYTYPE_BREAKDOWN_VEC",
    "JITTER": "KEYTYPE_JITTER_VEC",
    "MOVING_HOLD": "KEYTYPE_MOVING_HOLD_VEC",
}


class LayerTraits(Flag):
    """Layer traits."""

    NONE = 0
    ACTIVE = auto()
    UNLOCKED = auto()
    SELECTED = auto()


class FrameTraits(Flag):
    """Frame traits."""

    NONE = 0
    SELECTED = auto()
    TAG = auto()


def layer_options_to_traits(
    active: bool = False, unlocked: bool = False, selected: bool = False
) -> LayerTraits:
    """Convert boolean layer options to LayerTraits.

    :param active: Active Layer
    :param unlocked: Unlocked Layer
    :param selected: Selected Layer
    :return: The matching LayerTraits filter
    """
    traits = LayerTraits.NONE
    if active:
        traits |= LayerTraits.ACTIVE
    if unlocked:
        traits |= LayerTraits.UNLOCKED
    if selected:
        traits |= LayerTraits.SELECTED
    return traits


def frame_options_to_traits(
    selected: bool = False, onion_tag: bool = False
) -> FrameTraits:
    """Convert boolean frame options to FrameTraits.

    :param selected: Selected Frame
    :param onion_tag: Frame tagged for onion skinning
    :return: The matching FrameTraits filter
    """
    traits = FrameTraits.NONE
    if selected:
        traits |= FrameTraits.SELECTED
    if onion_tag:
        traits |= FrameTraits.TAG
    return traits


def get_gp_layers(
    gp: bpy.types.GreasePencil, layer_filter: LayerTraits = LayerTraits.NONE
) -> list[bpy.types.GPencilLayer]:
    """
    Return GreasePencil layers matching the optional `layer_filter` flags.

    :param gp: The GreasePencil data
    :param layer_filter: Layer filter flags
    """
    return [
        layer
        for layer in gp.layers
        if (
            (LayerTraits.ACTIVE not in layer_filter or layer == gp.layers.active)
            and (LayerTraits.UNLOCKED not in layer_filter or not layer.lock)
            and (LayerTraits.SELECTED not in layer_filter or layer.select)
        )
    ]


def get_gp_keyframes(
    gp: bpy.types.GreasePencil,
    layer_filter: LayerTraits = LayerTraits.NONE,
    frame_filter: FrameTraits = FrameTraits.NONE,
    frame_min: int = 0,
    frame_max: int = sys.maxsize,
) -> list[bpy.types.GPencilFrame]:
    """
    Return `gp`'s keyframes on layers matching `layer_filter` and `frame_filter`
    within the range defined by `frame_min` and `frame_max`.

    :param gp: The GreasePencil data
    :param layer_filter: Layer filter flags
    :param frame_filter: Frame filter flags
    :param frame_min: Frame range min value
    :param frame_max: Frame range max value
    :returns: The list of GPencilFrames sorted by ascending frame_number
    """
    keyframes: list[bpy.types.GPencilFrame] = []
    for layer in get_gp_layers(gp, layer_filter):
        keyframes += [
            f
            for f in layer.frames
            if (
                (frame_min <= f.frame_number <= frame_max)
                and (FrameTraits.SELECTED not in frame_filter or f.select)
                and (FrameTraits.TAG not in frame_filter or f.tag)
            )
        ]

    return sorted(keyframes, key=lambda f: f.frame_number)


def get_active_gp_keyframe(
    gpd: bpy.types.GreasePencil,
) -> Optional[bpy.types.GPencilFrame]:
    return gpd.layers.active.active_frame if gpd.layers.active else None


def gp_compute_list_of_frames_to_duplicate(
    gpl: bpy.types.GPencilLayer, frame_numbers: list[int]
) -> list[tuple[bpy.types.GPencilFrame, int]]:
    """
    Compute a list that indicates what keyframe needs to be copied to what frame based on a list of frames.
    The keyframes will be duplicated from the keyframe that is visible at the specified frame number in the list `frame_numbers`.

    :param gpl: The GreasePencilLayer.
    :param frame_numbers: Frame numbers to create the frames on.
    :returns: A list of tuples with the frame to duplicate and the target frame number.
    """
    if len(gpl.frames) == 0:
        return []

    new_frames_list = []

    i = 0
    # If the target is before the first key, skip it
    while frame_numbers[i] < gpl.frames[0].frame_number:
        i += 1

    j = 0
    while i < len(frame_numbers):
        target = frame_numbers[i]
        current_key = gpl.frames[j].frame_number

        # If there is already a keyframe at the target, skip it
        if target == current_key:
            i += 1
            continue

        # target > current:
        if j + 1 < len(gpl.frames):
            next_key = gpl.frames[j + 1].frame_number

            # If the next key is after the target, copy the current key and got to the next target
            if target < next_key:
                new_frames_list.append((gpl.frames[j], target))
                i += 1
            # Else go to the next key
            else:
                j += 1
        else:
            # If this is the last key, copy it and got to the next target
            new_frames_list.append((gpl.frames[j], target))
            i += 1

    return new_frames_list


def gp_create_new_duplicated_frames(
    gpl: bpy.types.GPencilLayer, frame_numbers: list[int], keyframe_type="KEYFRAME"
):
    """
    Create new gp keyframes based on the frame numbers in `frame_numbers`.
    The created frames will be duplicates of the visible frame at their respective time.

    :param gpl: The GreasePencilLayer
    :param frame_numbers: Frame numbers to create the frames on
    :param keyframe_type: The keyframe type for the new frames
    """

    # Get a list of the frames to duplicate
    new_frames_list = gp_compute_list_of_frames_to_duplicate(gpl, frame_numbers)

    # Create the new keyframes
    for gpf, target_nr in new_frames_list:
        new_gpf: bpy.types.GPencilFrame = gpl.frames.copy(gpf, frame_number=target_nr)
        new_gpf.keyframe_type = keyframe_type


def shift_keyframes(
    keyframes: list[bpy.types.GPencilFrame],
    offset: int,
    frame_min: int = 0,
    adjust_offset: bool = False,
):
    """
    Shift `keyframes` by `offset` with `frame_min` as a minimum frame value constraint.

    :param keyframes: The keyframes to consider
    :param offset: The offset to apply
    :param frame_min: The minimum frame value constraint
    :param adjust_offset: Whether to adjust offset to satisfy `frame_min` constraint
    :returns: Whether keyframes were shifted
    """
    min_value = min(keyframes, key=lambda x: x.frame_number).frame_number
    # If keyframes contains keys below frame_min, return
    if min_value < frame_min:
        return False

    # If offset makes the new minimum value below acceptable minimum frame value:
    if min_value + offset < frame_min:
        # - adjust offset if option is enabled
        if adjust_offset:
            offset = frame_min - min_value
        # - otherwise, do nothing and return
        else:
            return False

    if offset == 0:
        return False

    # Offset keyframes
    for keyframe in keyframes:
        keyframe.frame_number += offset

    return True


def shift_gp_keyframes(
    gp: bpy.types.GreasePencil,
    frame_start: int,
    offset: int = 1,
    adjust_offset: bool = False,
    only_active_layer: bool = False,
    only_unlocked_layers: bool = False,
    only_selected_layers: bool = False,
) -> list[bpy.types.GPencilFrame]:
    """Shift `gp` keyframes after `frame_start` by `offset`.

    :param gp: The GreasePencil data to consider
    :param frame_start: The frame after which keyframes are shifted
    :param offset: The offset to apply
    :param adjust_offset: Whether to adjust offset to keep keyframes above `frame_start`
    :param only_active_layer: Only affect active layer
    :param only_unlocked_layers: Only affect unlocked layers
    :param only_selected_layers: Only affect selected layers
    :returns: The keyframes moved by this operation
    """

    # Get GP keyframes after frame_start
    keyframes = get_gp_keyframes(
        gp,
        layer_options_to_traits(
            only_active_layer, only_unlocked_layers, only_selected_layers
        ),
        frame_min=frame_start + 1,
    )

    if not keyframes:
        return []

    res = shift_keyframes(
        keyframes, offset, frame_start + 1, adjust_offset=adjust_offset
    )

    return keyframes if res else []
