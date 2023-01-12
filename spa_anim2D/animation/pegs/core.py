# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from dataclasses import dataclass
from math import inf, sqrt
import sys
from typing import List, Tuple
from mathutils import Vector
import bpy


PEGS_ROOT_BONE_PREFIX = ".root_"
PEGS_OFFSET_BONE_PREFIX = ".offset_"


@dataclass
class Plane3D:
    co: Vector
    u: Vector
    v: Vector


@dataclass
class BoundingBox3D:
    min: Vector
    max: Vector


def refresh_peg_transformation_gizmo(context: bpy.types.Context):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if (
        tool is not None
        and tool.mode == "PAINT_GPENCIL"
        and tool.widget == "ANIM_GGT_pegs_transform_widget"
    ):
        bpy.ops.wm.tool_set_by_id(name="builtin.transform_pegs")


def get_bounding_box_dimensions(bbox: BoundingBox3D):
    return Vector(bbox.max - bbox.min)


def get_bounding_box_center(bbox: BoundingBox3D):
    return Vector((bbox.min + bbox.max) / 2)


def get_frames_bounding_box(frames: List[bpy.types.GPencilFrame]):
    bounding_box_max = Vector((-inf, -inf, -inf))
    bounding_box_min = Vector((inf, inf, inf))
    found = False
    for gpf in frames:
        if bbox := get_frame_bounding_box(gpf):
            bounding_box_min = Vector(
                (min(bounding_box_min[i], bbox.min[i]) for i in range(3))
            )
            bounding_box_max = Vector(
                (max(bounding_box_max[i], bbox.max[i]) for i in range(3))
            )
            found = True

    return BoundingBox3D(bounding_box_min, bounding_box_max) if found else None


def get_custom_shape_bounding_box(ob: bpy.types.Object):
    bounding_box_max = Vector((-inf, -inf, -inf))
    bounding_box_min = Vector((inf, inf, inf))

    for x in ob.bound_box:
        v = Vector(x)
        bounding_box_min = Vector((min(bounding_box_min[i], v[i]) for i in range(3)))
        bounding_box_max = Vector((max(bounding_box_max[i], v[i]) for i in range(3)))

    return BoundingBox3D(bounding_box_min, bounding_box_max)


def get_frame_bounding_box(gpf: bpy.types.GPencilFrame):
    if not gpf:
        return None

    if len(gpf.strokes) < 1:
        return None

    bounding_box_max = Vector((-inf, -inf, -inf))
    bounding_box_min = Vector((inf, inf, inf))
    for gps in gpf.strokes:
        bounding_box_min = Vector(
            (min(bounding_box_min[i], gps.bound_box_min[i]) for i in range(3))
        )
        bounding_box_max = Vector(
            (max(bounding_box_max[i], gps.bound_box_max[i]) for i in range(3))
        )

    # Compute bounding box rectangle with frame transformation applied.
    if bpy.context.tool_settings.use_gpencil_offset_frames:
        bl = bounding_box_min.copy()
        br = Vector((bounding_box_max[0], bounding_box_min[1], bounding_box_min[2]))
        tr = bounding_box_max.copy()
        tl = Vector((bounding_box_min[0], bounding_box_min[1], bounding_box_max[2]))

        bounding_box_max = Vector((-inf, -inf, -inf))
        bounding_box_min = Vector((inf, inf, inf))

        for corner in (bl, br, tr, tl):
            corner = gpf.offset @ corner

            bounding_box_min = Vector(
                (min(bounding_box_min[i], corner[i]) for i in range(3))
            )
            bounding_box_max = Vector(
                (max(bounding_box_max[i], corner[i]) for i in range(3))
            )

    return BoundingBox3D(bounding_box_min, bounding_box_max)


def get_parented_layers_from_offset_bone_name(
    gpd: bpy.types.GreasePencil, offset_bone_name: str
):
    parented_layers = []
    for gpl in gpd.layers:
        if gpl.parent_bone == offset_bone_name:
            parented_layers.append(gpl)

    return parented_layers


def get_parented_layers_from_bone_group(
    gpd: bpy.types.GreasePencil, bone_group: bpy.types.BoneGroup
):
    armature_object: bpy.types.Object
    if not (armature_object := gpd.pegbar_object):
        return None

    _, offset = get_pose_bones_from_peg_bone_group(armature_object, bone_group)
    if not offset:
        return None

    return get_parented_layers_from_offset_bone_name(gpd, offset.name)


def get_armature_bones_active_bone_index_value(self: bpy.types.Armature):
    bone = self.bones.active
    if not bone:
        return -1
    return self.bones.find(bone.name)


def get_pose_active_bone_group_index_value(self: bpy.types.Object):
    if self.type != "ARMATURE":
        return -1
    return self.pose.bone_groups.active_index


def set_pose_active_bone_group_index_value(self: bpy.types.Object, value: int):
    if self.type != "ARMATURE":
        return

    pose = self.pose
    if not (0 <= value < len(pose.bone_groups)):
        return

    pose.bone_groups.active_index = value

    root, _ = get_bones_from_peg_bone_group(self, pose.bone_groups.active)
    if root:
        self.data.bones.active = root
        refresh_peg_transformation_gizmo(bpy.context)


def peg_keyframe(
    root_bone: bpy.types.PoseBone, offset_bone: bpy.types.PoseBone, group_name: str
):
    root_bone.keyframe_insert("location", index=0, group=group_name)
    root_bone.keyframe_insert("location", index=2, group=group_name)

    offset_bone.keyframe_insert("location", index=0, group=group_name)
    offset_bone.keyframe_insert("location", index=2, group=group_name)
    offset_bone.keyframe_insert("rotation_euler", index=1, group=group_name)
    offset_bone.keyframe_insert("scale", index=0, group=group_name)
    offset_bone.keyframe_insert("scale", index=2, group=group_name)


def get_pose_bones_from_peg_bone_group(
    armature_object: bpy.types.Object, bone_group: bpy.types.BoneGroup
) -> Tuple[bpy.types.PoseBone, bpy.types.PoseBone]:
    for pose_bone in armature_object.pose.bones:
        if pose_bone.bone_group == bone_group and pose_bone.name.startswith(
            PEGS_OFFSET_BONE_PREFIX
        ):
            return (pose_bone.parent, pose_bone)
    return (None, None)


def get_bones_from_peg_bone_group(
    armature_object: bpy.types.Object, bone_group: bpy.types.BoneGroup
) -> Tuple[bpy.types.Bone, bpy.types.Bone]:
    root, offset = get_pose_bones_from_peg_bone_group(armature_object, bone_group)
    if root and offset:
        return (
            armature_object.data.bones[root.name],
            armature_object.data.bones[offset.name],
        )
    return (None, None)


def peg_rename(
    armature_object: bpy.types.Object, bone_group: bpy.types.BoneGroup, new_name: str
):
    old_name = bone_group.name
    bone_group.name = new_name
    if armature_object.animation_data:
        if action := armature_object.animation_data.action:
            action.groups[old_name].name = bone_group.name

    root_bone, offset_bone = get_bones_from_peg_bone_group(armature_object, bone_group)
    root_bone.name = f"{PEGS_ROOT_BONE_PREFIX}{bone_group.name}"
    offset_bone.name = f"{PEGS_OFFSET_BONE_PREFIX}{bone_group.name}"


# Ported from Blenders `ortho_basis_v3v3_v3`. We want to make sure these behave the same.
def ortho_basis_v3v3_v3(n: Vector) -> Tuple[Vector, Vector]:
    eps = sys.float_info.epsilon
    f = n.length_squared

    r_n1 = Vector()
    r_n2 = Vector()

    if f > eps:
        d = 1.0 / sqrt(f)

        r_n1.xyz = (n.y * d, -n.x * d, 0.0)
        r_n2.xyz = (-n.z * r_n1.y, n.z * r_n1.x, n.x * r_n1.y - n.y * r_n1.x)
    else:
        # degenerate case
        r_n1.x = -1.0 if (n.z < 0.0) else 1.0
        r_n1.y = r_n1.z = r_n2.x = r_n2.z = 0.0
        r_n2.y = 1.0

    return r_n1, r_n2


def local_space_to_transform_plane_space(plane: Plane3D, co_3d: Vector):
    tmp: Vector = co_3d - plane.co
    return Vector((tmp.dot(plane.u), tmp.dot(plane.v)))


def transform_plane_space_to_local_space(plane: Plane3D, co_2d: Vector):
    tmp: Vector = plane.co.copy()
    tmp += plane.u * co_2d.x
    tmp += plane.v * co_2d.y
    return tmp


def register():
    # Pointer property that points to the armature that is used for the pegbar system
    bpy.types.GreasePencil.pegbar_object = bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Pegbar System",
        options=set(),
    )

    # Pointer property that points to the object used as the custom shape for the bones in the pegbar system
    bpy.types.GreasePencil.peg_shape = bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Peg Shape",
        options=set(),
    )

    # Index of the active bone in the armature.
    bpy.types.Armature.active_bone_index = bpy.props.IntProperty(
        name="Active Bone Index",
        get=get_armature_bones_active_bone_index_value,
        default=-1,
        options=set(),
    )

    # Index of the active bone group.
    bpy.types.Object.active_bone_group_index = bpy.props.IntProperty(
        name="Active Bone Group Index",
        get=get_pose_active_bone_group_index_value,
        set=set_pose_active_bone_group_index_value,
        default=-1,
        options=set(),
    )


def unregister():
    del bpy.types.GreasePencil.pegbar_object
    del bpy.types.GreasePencil.peg_shape
    del bpy.types.Armature.active_bone_index
    del bpy.types.Object.active_bone_group_index
