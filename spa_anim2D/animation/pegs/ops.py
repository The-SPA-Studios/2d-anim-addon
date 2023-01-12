# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import os
import bpy

from spa_anim2D.utils import get_addon_directory, register_classes, unregister_classes
from spa_anim2D.animation.core import gp_create_new_duplicated_frames
from spa_anim2D.animation.pegs.core import (
    get_bones_from_peg_bone_group,
    get_bounding_box_center,
    get_frames_bounding_box,
    get_parented_layers_from_offset_bone_name,
    refresh_peg_transformation_gizmo,
    peg_keyframe,
    peg_rename,
    get_pose_bones_from_peg_bone_group,
    PEGS_OFFSET_BONE_PREFIX,
    PEGS_ROOT_BONE_PREFIX,
)

from mathutils import Vector, Matrix


def gpencil_pegbar_system_poll(context: bpy.types.Context):
    return (
        context.active_object
        and context.active_object.type == "GPENCIL"
        and context.active_object.data.pegbar_object
    )


class ANIM_OT_pegbar_create(bpy.types.Operator):
    bl_idname = "anim.pegbar_create"
    bl_label = "Create Pegbar"
    bl_description = "Create a pegbar on the active grease pencil object"
    bl_options = {"UNDO", "REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.active_object and context.active_object.type == "GPENCIL"

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data

        # Pegbar system already exists.
        if gpd.pegbar_object:
            return {"CANCELLED"}

        armature: bpy.types.Armature = bpy.data.armatures.new("Pegbar_Armature")
        armature_object = bpy.data.objects.new(name="Pegbar", object_data=armature)

        armature_object.parent = ob

        for collection in ob.users_collection:
            collection.objects.link(armature_object)

        # Set the custom property to point to the armature.
        gpd.pegbar_object = armature_object

        # Import the custom shape
        if not (peg_shape := bpy.data.objects.get("_PegCustomShape")):
            addon_path = get_addon_directory()
            obj_path = "resources/blend/peg_custom_shape.blend"
            try:
                with bpy.data.libraries.load(
                    os.path.join(addon_path, obj_path), link=False
                ) as (data_from, data_to):
                    data_to.objects = data_from.objects
                peg_shape = data_to.objects[0]
            except OSError:
                self.report({"ERROR"}, "Could not load custom shape!")

        # Set the custom shape property
        gpd.peg_shape = peg_shape

        # Add a new peg
        bpy.ops.anim.peg_add()

        return {"FINISHED"}


class ANIM_OT_peg_add(bpy.types.Operator):
    bl_idname = "anim.peg_add"
    bl_label = "Add New Peg"
    bl_description = "Add a new peg to the pegbar system"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(
        name="Name", description="Name of the peg", default="Peg", options={"SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return gpencil_pegbar_system_poll(context)

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object
        armature: bpy.types.Armature = armature_object.data

        # Set the armature as the active object
        context.view_layer.objects.active = armature_object

        # Add the bone in edit mode
        bpy.ops.object.mode_set(mode="EDIT", toggle=False)

        bpy.ops.armature.bone_primitive_add(name=f"{PEGS_ROOT_BONE_PREFIX}{self.name}")
        peg_root_name = armature.edit_bones[-1].name

        bpy.ops.armature.bone_primitive_add(
            name=f"{PEGS_OFFSET_BONE_PREFIX}{self.name}"
        )
        peg_offset_name = armature.edit_bones[-1].name

        # Position the bones
        for name in (peg_root_name, peg_offset_name):
            bone = armature.edit_bones[name]
            bone.head = Vector()
            bone.tail = Vector((0, 1, 0))

        armature.edit_bones[peg_offset_name].parent = armature.edit_bones[peg_root_name]

        bpy.ops.object.mode_set(mode="POSE", toggle=False)

        # Create a bone group for the peg
        bone_group = armature_object.pose.bone_groups.new(name=self.name)
        armature_object.pose.bone_groups.active = bone_group

        root_bone = armature_object.pose.bones[peg_root_name]
        offset_bone = armature_object.pose.bones[peg_offset_name]

        for bone in (root_bone, offset_bone):
            # Lock the location, rotation and scale so that the bone is constrained in the X-Z plane
            bone.lock_location = False, True, False
            bone.lock_rotation = True, False, True
            bone.lock_scale = True, False, True
            # Set the rotation mode
            bone.rotation_mode = "XYZ"

            # Set the group name
            bone.bone_group = bone_group

            # Set the pegbar shape
            bone.custom_shape = gpd.peg_shape
            bone.custom_shape_scale_xyz = (0, 0, 0)

        # Key the bones
        peg_keyframe(root_bone, offset_bone, bone_group.name)

        # Reset the mode (flush changes)
        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

        armature_object.active_bone_group_index = (
            armature_object.pose.bone_groups.active_index
        )

        context.view_layer.objects.active = ob

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_remove(bpy.types.Operator):
    bl_idname = "anim.peg_remove"
    bl_label = "Remove Active Peg"
    bl_description = "Remove the active peg from the pegbar system"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(
        name="Name", description="Name of the peg", default="Peg", options={"SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            gpencil_pegbar_system_poll(context)
            and context.active_object.data.pegbar_object.data.bones.active
        )

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object
        armature: bpy.types.Armature = armature_object.data

        pose = armature_object.pose
        # Check if the bone group exits
        if not (bone_group := pose.bone_groups.get(self.name)):
            return {"CANCELLED"}

        root, offset = get_bones_from_peg_bone_group(armature_object, bone_group)

        # Remove the parent of all the layers that are parented to this bone
        parented_layers = get_parented_layers_from_offset_bone_name(gpd, offset.name)
        for gpl in parented_layers:
            gpl.parent_bone = ""
            gpl.parent_type = "OBJECT"

            gpl.matrix_inverse = Matrix()

        # Set the armature as the active object
        context.view_layer.objects.active = armature_object

        # Compute active bone index after bone deletion.
        updated_bone_group_index = min(
            pose.bone_groups.active_index, len(pose.bone_groups) - 2
        )

        # Remove animation data of this peg
        if armature_object.animation_data and armature_object.animation_data.action:
            action_groups = armature_object.animation_data.action.groups
            if bone_group.name in action_groups:
                action_groups.remove(action_groups[bone_group.name])

            fcurves = armature_object.animation_data.action.fcurves
            for f in fcurves:
                if f.data_path.startswith(
                    f'pose.bones["{root.name}"]'
                ) or f.data_path.startswith(f'pose.bones["{offset.name}"]'):
                    fcurves.remove(f)

        # Remove the bone in edit mode
        bpy.ops.object.mode_set(mode="EDIT", toggle=False)
        armature.edit_bones.remove(armature.edit_bones[root.name])
        armature.edit_bones.remove(armature.edit_bones[offset.name])
        bpy.ops.object.mode_set(mode="POSE", toggle=False)

        # Remove the bone group
        armature_object.pose.bone_groups.remove(bone_group)

        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

        armature_object.active_bone_group_index = updated_bone_group_index

        context.view_layer.objects.active = ob

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_rename(bpy.types.Operator):
    bl_idname = "anim.peg_rename"
    bl_label = "Rename Peg"
    bl_description = "Rename a peg"
    bl_options = {"UNDO", "REGISTER"}
    bl_property = "new_name"

    name: bpy.props.StringProperty(
        name="Name",
        description="Name of the peg to rename",
        default="",
        options={"SKIP_SAVE", "HIDDEN"},
    )

    new_name: bpy.props.StringProperty(
        name="New Name",
        description="New name of the peg",
        default="",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return gpencil_pegbar_system_poll(context)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        if not (bone_group := armature_object.pose.bone_groups.get(self.name)):
            return {"CANCELLED"}

        if self.new_name == "":
            return {"CANCELLED"}

        peg_rename(armature_object, bone_group, self.new_name)

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_parent_active_layer(bpy.types.Operator):
    bl_idname = "anim.peg_parent_active_layer"
    bl_label = "Parent Active Layer To Peg"
    bl_description = "Parent the active layer in the grease pencil object to the peg"
    bl_options = {"UNDO", "REGISTER"}

    unparent: bpy.props.BoolProperty(
        name="Unparent", default=False, options={"SKIP_SAVE"}
    )
    peg_name: bpy.props.StringProperty(
        name="Peg Name", default="", options={"SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            gpencil_pegbar_system_poll(context)
            and context.active_object.data.pegbar_object.data.bones.active
        )

    def execute(self, context: bpy.types.Context):
        ts: bpy.types.ToolSettings = context.tool_settings
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object
        armature: bpy.types.Armature = armature_object.data

        gpl = gpd.layers.active

        if self.unparent:
            gpl.parent_bone = ""
            gpl.parent_type = "OBJECT"

            gpl.matrix_inverse = Matrix()
            return {"FINISHED"}

        # Check if the bone group exits
        if not (bone_group := armature_object.pose.bone_groups.get(self.peg_name)):
            return {"CANCELLED"}

        root_pose_bone, offset_pose_bone = get_pose_bones_from_peg_bone_group(
            armature_object, bone_group
        )
        offset_bone = armature.bones[offset_pose_bone.name]

        gpl.parent = armature_object
        gpl.parent_type = "BONE"
        gpl.parent_bone = offset_bone.name

        if layers := get_parented_layers_from_offset_bone_name(gpd, offset_bone.name):
            frames = [gpl.active_frame for gpl in layers]
            bbox = get_frames_bounding_box(frames)
            if bbox:
                center = get_bounding_box_center(bbox)

                # Move the pivot to the center of the
                translation_matrix = Matrix.Translation(center)
                root_pose_bone.matrix_basis = translation_matrix
                offset_pose_bone.matrix_basis = translation_matrix.inverted()

                if ts.use_keyframe_insert_auto:
                    bpy.ops.anim.peg_insert_keyframe()

        # Keep the transform
        gpl.matrix_inverse = offset_bone.matrix.to_4x4()

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_parent_active_peg(bpy.types.Operator):
    bl_idname = "anim.peg_parent_active_peg"
    bl_label = "Parent Active Peg To Peg"
    bl_description = "Parent the active peg in the grease pencil object to the peg"
    bl_options = {"UNDO", "REGISTER"}

    unparent: bpy.props.BoolProperty(
        name="Unparent", default=False, options={"SKIP_SAVE"}
    )

    peg_name: bpy.props.StringProperty(
        name="Peg Name", default="", options={"SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return gpencil_pegbar_system_poll(context)

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object
        armature: bpy.types.Armature = armature_object.data

        active_bone_group = armature_object.pose.bone_groups.active
        active_root, _ = get_pose_bones_from_peg_bone_group(
            armature_object, active_bone_group
        )

        if self.unparent:
            parent_bone = None
        else:
            # Check if the bone group exits
            if not (bone_group := armature_object.pose.bone_groups.get(self.peg_name)):
                return {"CANCELLED"}

            _, target_offset = get_pose_bones_from_peg_bone_group(
                armature_object, bone_group
            )

        # Set the armature as the active object
        context.view_layer.objects.active = armature_object

        # Parent the bone in edit mode
        bpy.ops.object.mode_set(mode="EDIT", toggle=False)

        if not self.unparent:
            parent_bone = armature.edit_bones[target_offset.name]

        bone = armature.edit_bones[active_root.name]
        bone.parent = parent_bone
        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

        context.view_layer.objects.active = ob

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_hide(bpy.types.Operator):
    bl_idname = "anim.peg_hide"
    bl_label = "Hide peg"
    bl_description = "Hide the peg from the view"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(
        name="Peg Name", default="", options={"HIDDEN", "SKIP_SAVE"}
    )
    hide: bpy.props.BoolProperty(name="Hide", default=True, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return gpencil_pegbar_system_poll(context)

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        # Check if the bone group exits
        if not (bone_group := armature_object.pose.bone_groups.get(self.name)):
            return {"CANCELLED"}

        root_bone, offset_bone = get_bones_from_peg_bone_group(
            armature_object, bone_group
        )

        root_bone.hide = offset_bone.hide = self.hide

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_mute_action(bpy.types.Operator):
    bl_idname = "anim.peg_mute_action"
    bl_label = "Mute peg action"
    bl_description = "Mute the action of the peg"
    bl_options = {"UNDO", "REGISTER"}

    name: bpy.props.StringProperty(
        name="Peg Name", default="", options={"HIDDEN", "SKIP_SAVE"}
    )
    unmute: bpy.props.BoolProperty(name="Unmute", default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            gpencil_pegbar_system_poll(context)
            and context.active_object.data.pegbar_object.animation_data
        )

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        # Check if the bone group exits
        if not (bone_group := armature_object.pose.bone_groups.get(self.name)):
            return {"CANCELLED"}

        # Check if the peg has animation data
        if not (
            anim_data := armature_object.animation_data.action.groups.get(self.name)
        ):
            return {"CANCELLED"}

        if not self.unmute:
            root_bone, offset_bone = get_pose_bones_from_peg_bone_group(
                armature_object, bone_group
            )

            root_bone.matrix = Matrix()
            offset_bone.matrix = Matrix()

            anim_data.mute = True
        else:
            # FIXME: Evil hack
            context.scene.frame_current = context.scene.frame_current
            anim_data.mute = False

        refresh_peg_transformation_gizmo(context)

        return {"FINISHED"}


class ANIM_OT_peg_insert_keyframe(bpy.types.Operator):
    bl_idname = "anim.peg_insert_keyframe"
    bl_label = "Insert Peg Keyframe"
    bl_description = "Insert a keyframe for the active peg"
    bl_options = {"UNDO", "REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            gpencil_pegbar_system_poll(context)
            and context.active_object.data.pegbar_object.animation_data
            and context.active_object.data.pegbar_object.data.bones.active
        )

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        # Set the armature as the active object
        context.view_layer.objects.active = armature_object
        bpy.ops.object.mode_set(mode="POSE", toggle=False)

        bone_group = armature_object.pose.bone_groups.active
        root, offset = get_pose_bones_from_peg_bone_group(armature_object, bone_group)
        peg_keyframe(root, offset, bone_group.name)

        # Reset the mode (flush changes)
        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)
        context.view_layer.objects.active = ob

        return {"FINISHED"}


class ANIM_OT_peg_reset_transform(bpy.types.Operator):
    bl_idname = "anim.peg_reset_transform"
    bl_label = "Reset Peg Transform"
    bl_description = "Reset the transformation of the active peg"
    bl_options = {"UNDO", "REGISTER"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            gpencil_pegbar_system_poll(context)
            and context.active_object.data.pegbar_object.animation_data
            and context.active_object.data.pegbar_object.data.bones.active
        )

    def execute(self, context: bpy.types.Context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object
        ts = context.tool_settings

        # Set the armature as the active object
        context.view_layer.objects.active = armature_object

        bpy.ops.object.mode_set(mode="POSE", toggle=False)

        bone_group = armature_object.pose.bone_groups.active

        root, offset = get_pose_bones_from_peg_bone_group(armature_object, bone_group)

        root.location = (0, 0, 0)
        root.rotation_euler = (0, 0, 0)
        root.scale = (1, 1, 1)

        offset.location = (0, 0, 0)
        offset.rotation_euler = (0, 0, 0)
        offset.scale = (1, 1, 1)

        if ts.use_keyframe_insert_auto:
            peg_keyframe(root, offset, bone_group.name)

        # Reset the mode (flush changes)
        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)
        context.view_layer.objects.active = ob

        return {"FINISHED"}


class ANIM_OT_peg_select(bpy.types.Operator):
    bl_idname = "anim.peg_select"
    bl_label = "Select a Peg"
    bl_description = "Select the peg under the mouse cursor"
    bl_options = {"UNDO", "REGISTER"}

    bl_keymaps = [
        {
            "key": "LEFTMOUSE",
            "alt": True,
            "properties": {},
        },
    ]

    @classmethod
    def poll(cls, context: bpy.types.Context):
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        return gpencil_pegbar_system_poll(context) and (
            tool.mode == "PAINT_GPENCIL"
            and tool.widget == "ANIM_GGT_pegs_transform_widget"
        )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        # Set the armature as the active object
        context.view_layer.objects.active = armature_object

        # Go to pose mode
        bpy.ops.object.mode_set(mode="POSE", toggle=False)
        bpy.ops.view3d.select(
            deselect_all=True,
            location=(event.mouse_region_x, event.mouse_region_y),
        )

        # Reset the mode (flush changes)
        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)
        bpy.ops.view3d.select(deselect_all=True)

        bone_group = armature_object.pose.bones[
            armature_object.data.active_bone_index
        ].bone_group
        armature_object.pose.bone_groups.active = bone_group

        armature_object.active_bone_group_index = (
            armature_object.pose.bone_groups.active_index
        )

        context.view_layer.objects.active = ob

        return {"FINISHED"}


class ANIM_OT_peg_bake_active_layer(bpy.types.Operator):
    bl_idname = "anim.peg_bake_active_layer"
    bl_label = "Bake Layer Transfrom"
    bl_description = "Bake the peg transformation of the active layer"
    bl_options = {"UNDO", "REGISTER"}

    create_inbetweens: bpy.props.BoolProperty(
        name="Create Inbetweens", default=False, options={"SKIP_SAVE"}
    )

    step_size: bpy.props.IntProperty(
        name="Step Size", default=1, min=1, soft_min=1, options={"SKIP_SAVE"}
    )

    def draw(self, _context):
        self.layout.use_property_split = True
        row = self.layout.row()
        row.prop(self, "create_inbetweens")

        row = self.layout.row()
        row.enabled = self.create_inbetweens
        row.prop(self, "step_size")

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return (
            gpencil_pegbar_system_poll(context)
            and context.active_object.data.layers.active
            and context.active_object.data.layers.active.parent_bone != ""
        )

    def execute(self, context: bpy.types.Context):
        scene: bpy.types.Scene = context.scene
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        gpl: bpy.types.GPencilLayer = gpd.layers.active
        if (
            gpl.parent_bone not in armature_object.pose.bones.keys()
            or not armature_object.animation_data
        ):
            return {"CANCELLED"}

        initial_frame = scene.frame_current
        bone_name = gpl.parent_bone

        # Remove the parent
        gpl.parent_bone = ""
        gpl.parent_type = "OBJECT"
        gpl.matrix_inverse = Matrix()

        # Make sure there is a grease pencil frame for each keyframe in the action of the BoneGroup
        frames = sorted(
            list(
                {
                    int(k.co[0])
                    for fcurve in armature_object.animation_data.action.fcurves
                    if fcurve.group.name
                    == armature_object.pose.bones[bone_name].bone_group.name
                    for k in fcurve.keyframe_points
                }
            )
        )
        # Create keyframes for where there are keys on the parent
        gp_create_new_duplicated_frames(gpl, frames, keyframe_type="KEYFRAME")

        if self.create_inbetweens:
            frame_range = list(
                range(
                    gpl.frames[0].frame_number,
                    max(gpl.frames[-1].frame_number, frames[-1]) + 1,
                    self.step_size,
                )
            )
            # Filter out previous keyframes
            frames = [f for f in frame_range if f not in frames]
            # Create inbetween frames
            gp_create_new_duplicated_frames(
                gpl, sorted(frames), keyframe_type="BREAKDOWN"
            )

        context.view_layer.objects.active = armature_object
        bpy.ops.object.mode_set(mode="POSE", toggle=False)
        bone = armature_object.pose.bones[bone_name]

        # Apply the parent transformation to all the strokes in the frame
        for gpf in gpl.frames:
            scene.frame_set(gpf.frame_number)
            gpf.transform(bone.matrix)

        bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

        context.view_layer.objects.active = ob

        scene.frame_current = initial_frame

        return {"FINISHED"}

    def invoke(self, context, _event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


classes = (
    ANIM_OT_pegbar_create,
    ANIM_OT_peg_add,
    ANIM_OT_peg_remove,
    ANIM_OT_peg_rename,
    ANIM_OT_peg_parent_active_layer,
    ANIM_OT_peg_parent_active_peg,
    ANIM_OT_peg_hide,
    ANIM_OT_peg_mute_action,
    ANIM_OT_peg_insert_keyframe,
    ANIM_OT_peg_reset_transform,
    ANIM_OT_peg_select,
    ANIM_OT_peg_bake_active_layer,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
