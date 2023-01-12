# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy
from spa_anim2D.drawing.core import get_active_gp_object

from spa_anim2D.animation.pegs.core import (
    Plane3D,
    get_bounding_box_center,
    get_bounding_box_dimensions,
    get_frames_bounding_box,
    get_custom_shape_bounding_box,
    get_parented_layers_from_offset_bone_name,
    get_pose_bones_from_peg_bone_group,
    get_bones_from_peg_bone_group,
    local_space_to_transform_plane_space,
    ortho_basis_v3v3_v3,
)

from spa_anim2D.utils import register_classes, unregister_classes

from mathutils import Matrix, Vector


class GPENCIL_UL_draw_pegbars(bpy.types.UIList):
    """
    Template to display the bones of an armature object (used as pegs).
    """

    bl_idname = "GPENCIL_UL_draw_pegbars"

    def draw_item(
        self,
        context,
        layout,
        data,
        item: bpy.types.BoneGroup,
        icon,
        active_data,
        active_propname,
        index,
    ):
        armature_object: bpy.types.Object = data.id_data
        root, _ = get_bones_from_peg_bone_group(armature_object, item)

        indentation = 0
        layout.separator(factor=0.5 * indentation)
        layout.label(text=item.name)

        if root.parent:
            root_parent = armature_object.pose.bones[root.parent.name]
            layout.label(text=root_parent.bone_group.name, icon="STATUSBAR")

        sub = layout.row(align=True)

        if (
            action := armature_object.animation_data.action
        ) and item.name in action.groups:
            anim_data = action.groups[item.name]
            # Mute action
            if not anim_data.mute:
                sub.operator(
                    "anim.peg_mute_action",
                    text="",
                    icon="RESTRICT_VIEW_OFF",
                    emboss=False,
                ).name = item.name
            else:
                props = sub.operator(
                    "anim.peg_mute_action",
                    text="",
                    icon="RESTRICT_VIEW_ON",
                    emboss=False,
                )
                props.name = item.name
                props.unmute = True

        # Visibility
        props = sub.operator(
            "anim.peg_hide",
            text="",
            icon="HIDE_ON" if root.hide else "HIDE_OFF",
            emboss=False,
        )
        props.name = item.name
        props.hide = not root.hide


class GPENCIL_MT_peg_parent(bpy.types.Menu):
    bl_idname = "GPENCIL_MT_peg_parent"
    bl_label = "Parent"
    bl_description = "Select the parent of the active peg"

    def draw(self, context):
        obj = get_active_gp_object()
        if not obj:
            return

        gpd = obj.data
        if not gpd.pegbar_object:
            return

        armature_object: bpy.types.Object = gpd.pegbar_object

        # First entry is there to unparent the peg.
        self.layout.operator("anim.peg_parent_active_peg", text=" - ").unparent = True

        active_bone_group = armature_object.pose.bone_groups.active
        active_root, _ = get_pose_bones_from_peg_bone_group(
            armature_object, active_bone_group
        )

        # Iterate through all the bones and create entries for them. Highlight the currently parented peg (if there is one).
        for bone_group in armature_object.pose.bone_groups:
            if bone_group == active_bone_group:
                continue

            _, offset = get_pose_bones_from_peg_bone_group(armature_object, bone_group)

            icon = "STATUSBAR" if offset == active_root.parent else "NONE"
            self.layout.operator(
                "anim.peg_parent_active_peg", text=bone_group.name, icon=icon
            ).peg_name = bone_group.name


class VIEW3D_PT_pegbar_system(bpy.types.Panel):
    bl_label = "Pegbars"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SPA.Anim2D"
    bl_parent_id = "VIEW3D_PT_draw_panel"

    def draw(self, _context: bpy.types.Context):
        obj = get_active_gp_object()
        if not obj:
            self.layout.label(text="No active Grease Pencil object")
            return

        gpd = obj.data
        if not gpd.pegbar_object:
            self.layout.operator("anim.pegbar_create")
            return

        armature_object: bpy.types.Object = gpd.pegbar_object
        if not armature_object:
            return

        # Active GP object layers list and tools
        row = self.layout.row()

        row.template_list(
            GPENCIL_UL_draw_pegbars.bl_idname,
            "",
            armature_object.pose,
            "bone_groups",
            armature_object,
            "active_bone_group_index",
            type="DEFAULT",
            columns=2,
            rows=3,
            sort_lock=True,
        )

        active_bone_group = armature_object.pose.bone_groups.active
        active_bone_group_name = active_bone_group.name if active_bone_group else ""

        col = row.column(align=True)
        col.operator("anim.peg_add", icon="ADD", text="")

        col = col.column(align=True)
        col.enabled = bool(active_bone_group)
        col.operator(
            "anim.peg_remove", icon="REMOVE", text=""
        ).name = active_bone_group_name

        col.separator()
        col.operator(
            "anim.peg_rename", icon="TEXT", text=""
        ).name = active_bone_group_name

        col.separator()
        col.operator("anim.peg_insert_keyframe", icon="KEY_HLT", text="")

        row = self.layout.row(heading="Parent")
        sub = row.split()

        root, offset = get_pose_bones_from_peg_bone_group(
            armature_object, active_bone_group
        )
        if not active_bone_group:
            text = ""
            icon = "NONE"
        else:
            text = root.parent.bone_group.name if root.parent else ""
            icon = "STATUSBAR" if root.parent else "NONE"
            sub.menu(
                GPENCIL_MT_peg_parent.bl_idname,
                text=text,
                icon=icon,
            )


def view3d_tool_poll(context: bpy.types.Context, name: str):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    return tool.idname == name


class PegsTransformWidgetGroup(bpy.types.GizmoGroup):
    bl_idname = "ANIM_GGT_pegs_transform_widget"
    bl_label = "Pegs Transform Widget"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT", "SHOW_MODAL_ALL"}

    root_bone = None
    offset_bone = None

    bbox = None
    parented_layers = None
    plane = None

    @classmethod
    def poll(cls, context):
        return (
            context.active_object
            and context.active_object.type == "GPENCIL"
            and context.active_object.mode == "PAINT_GPENCIL"
            and context.active_object.data.pegbar_object
            and view3d_tool_poll(context, "builtin.transform_pegs")
        )

    def is_modal(self):
        return any(gz.is_modal for gz in self.gizmos)

    def hide(self, hide=True):
        for gz in self.gizmos:
            gz.hide = hide

    # Unused
    def get_matrix(self):
        return None

    def set_matrix_gizmo_rs(self, value):
        matrix = Matrix([[v for v in value[row : row + 16 : 4]] for row in range(4)])
        self.offset_bone.matrix_basis = matrix @ Matrix.Translation(-self.center)

    def set_matrix_gizmo_t(self, value):
        matrix = Matrix([[v for v in value[row : row + 16 : 4]] for row in range(4)])

        _, offset_rot, offset_sca = self.initial_offset_matrix.decompose()
        offset_rot_matrix = offset_rot.to_matrix().to_4x4()
        offset_sca_matrix = Matrix.Diagonal(offset_sca).to_4x4()

        self.root_bone.matrix_basis.translation = (
            matrix
            @ self.initial_offset_matrix.inverted()
            @ offset_rot_matrix
            @ offset_sca_matrix
            @ Matrix.Translation(-self.center)
        ).translation

    def set_matrix_gizmo_p(self, value):
        matrix = Matrix([[v for v in value[row : row + 16 : 4]] for row in range(4)])
        self.root_bone.matrix_basis.translation = matrix.translation
        # Compute the inverse of the differential translation we just did.
        diff_translation = self.initial_root_matrix @ matrix.inverted()
        # Apply it to the translation of the offset bone's initial matrix.
        self.offset_bone.matrix_basis.translation = (
            diff_translation @ self.initial_offset_matrix
        ).translation

    def initialize(self, context):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object

        if not (bone_group := armature_object.pose.bone_groups.active):
            self.hide(True)
            return False

        root_bone, offset_bone = get_bones_from_peg_bone_group(
            armature_object, bone_group
        )

        if not root_bone or not offset_bone or root_bone.hide:
            self.hide(True)
            return False

        self.root_bone = armature_object.pose.bones[root_bone.name]
        self.offset_bone = armature_object.pose.bones[offset_bone.name]

        if action := armature_object.animation_data.action:
            action_groups = action.groups
            if root_bone.name in action_groups and action_groups[root_bone.name].mute:
                self.hide(True)
                return False

        if not self.plane:
            # Always use the X-Z plane for now
            u, v = ortho_basis_v3v3_v3(Vector((0, 1, 0)))
            self.plane = Plane3D(co=Vector(), u=u, v=v)

        self.parented_layers = get_parented_layers_from_offset_bone_name(
            gpd, offset_bone.name
        )

        self.hide(False)
        return True

    def setup_gizmo_rs(self, ob):
        offset_loc, offset_rot, offset_sca = self.offset_bone.matrix_basis.decompose()
        offset_rot_matrix = offset_rot.to_matrix().to_4x4()
        offset_sca_matrix = Matrix.Diagonal(offset_sca).to_4x4()

        self.gizmo_rs.offset = local_space_to_transform_plane_space(
            self.plane, self.offset_bone.matrix_basis @ self.center
        )
        # Use the local Y axis for the rotation
        self.gizmo_rs.angle = offset_rot.to_euler().y
        self.gizmo_rs.scale = offset_sca.xz

        self.gizmo_rs.pivot = local_space_to_transform_plane_space(
            self.plane,
            -offset_loc @ offset_rot_matrix @ offset_sca_matrix.inverted()
            - self.center,
        )

        # Use dimensions of the frame
        self.gizmo_rs.dimensions = (
            self.dims[0],
            self.dims[1],
        )

        self.gizmo_rs.matrix_basis = ob.matrix_world @ self.root_bone.matrix
        self.gizmo_rs.force_update = True

    def setup_gizmo_t(self, ob):
        _, offset_rot, offset_sca = self.offset_bone.matrix_basis.decompose()

        self.gizmo_t.offset = local_space_to_transform_plane_space(
            self.plane,
            self.root_bone.matrix_basis @ self.offset_bone.matrix_basis @ self.center,
        )
        # Use 95% of the dimensions of the frame
        self.gizmo_t.dimensions = (
            self.dims[0] * 0.95,
            self.dims[1] * 0.95,
        )
        self.gizmo_t.angle = offset_rot.to_euler().y
        self.gizmo_t.scale = offset_sca.xz

        parent_matrix = (
            self.root_bone.parent.matrix if self.root_bone.parent else Matrix()
        )
        self.gizmo_t.matrix_basis = ob.matrix_world @ parent_matrix
        self.gizmo_t.force_update = True

    def setup_gizmo_p(self, ob):
        loc, _, sca = self.root_bone.matrix_basis.decompose()
        self.gizmo_p.offset = local_space_to_transform_plane_space(self.plane, loc)
        # Compute a radius that takes the scale of the root bone into account.
        self.gizmo_p.radius = max(0.2, (0.2 * min(sca[0], sca[2])))

        # The parent space is the space of the parent of the root bone.
        # Since we want to both move the root and the offset.
        parent_matrix = (
            self.root_bone.parent.matrix if self.root_bone.parent else Matrix()
        )
        self.gizmo_p.matrix_basis = ob.matrix_world @ parent_matrix
        self.gizmo_p.force_update = True

    def setup_gizmos(self, context):
        ob: bpy.types.Object = context.active_object

        if not self.is_modal():
            self.initial_root_matrix = self.root_bone.matrix_basis.copy()
            self.initial_offset_matrix = self.offset_bone.matrix_basis.copy()

            self.bbox = None
            if self.parented_layers:
                self.bbox = get_frames_bounding_box(
                    [gpl.active_frame for gpl in self.parented_layers]
                )
            if not self.bbox:
                self.bbox = get_custom_shape_bounding_box(self.offset_bone.custom_shape)

        if self.bbox:
            self.center = get_bounding_box_center(self.bbox)
            # Dimensions in on the XZ plane
            self.dims = get_bounding_box_dimensions(self.bbox).xz

        self.setup_gizmo_rs(ob)
        self.setup_gizmo_t(ob)
        self.setup_gizmo_p(ob)

    def setup(self, context):
        # Create all the gizmos
        self.gizmo_rs = self.gizmos.new("GIZMO_GT_xform_plane3d")
        self.gizmo_t = self.gizmos.new("GIZMO_GT_xform_plane3d")
        self.gizmo_p = self.gizmos.new("GIZMO_GT_translate_plane3d")

        if not self.initialize(context):
            return

        # Always use the X-Z plane for now
        self.gizmo_rs.normal = self.gizmo_t.normal = self.gizmo_p.normal = (0, 1, 0)

        # Setup rotation/scale gizmo
        self.gizmo_rs.use_translation = False
        self.gizmo_rs.use_rotation = True
        self.gizmo_rs.use_scale = True
        self.gizmo_rs.use_skew = False
        self.gizmo_rs.use_pivot = False
        self.gizmo_rs.color = (0.07, 0.7, 0.07)
        self.gizmo_rs.use_tooltip = False

        # Setup translation gizmo
        self.gizmo_t.use_translation = True
        self.gizmo_t.use_rotation = False
        self.gizmo_t.use_scale = False
        self.gizmo_t.use_skew = False
        self.gizmo_t.use_pivot = False
        self.gizmo_t.color = (1, 0.7, 0.07)
        self.gizmo_t.line_width = 0.0
        self.gizmo_t.use_tooltip = False

        # Setup pivot gizmo
        self.gizmo_p.color = (0.8, 0.1, 0.8)
        self.gizmo_p.color_highlight = (1.0, 0.5, 1.0)
        self.gizmo_p.alpha = 1.0
        self.gizmo_p.use_tooltip = False
        self.gizmo_p.line_width = 2.0

        # Setup the gizmos in the right location, rotation and scale
        self.setup_gizmos(context)

        # Set the target handlers for all the gizmos
        # Keep this last.
        self.gizmo_rs.target_set_handler(
            target="matrix", get=self.get_matrix, set=self.set_matrix_gizmo_rs
        )
        self.gizmo_t.target_set_handler(
            target="matrix", get=self.get_matrix, set=self.set_matrix_gizmo_t
        )
        self.gizmo_p.target_set_handler(
            target="matrix", get=self.get_matrix, set=self.set_matrix_gizmo_p
        )

    def refresh(self, context):
        if not self.initialize(context):
            return

        self.setup_gizmos(context)

    def exit_cleanup(self, context: bpy.types.Context, _gizmo, cancel):
        ts = context.tool_settings
        if ts.use_keyframe_insert_auto and not cancel:
            bpy.ops.anim.peg_insert_keyframe()


class PegsTransformTool(bpy.types.WorkSpaceTool):
    bl_idname = "builtin.transform_pegs"
    bl_label = "Transform Pegs"
    bl_space_type = "VIEW_3D"
    bl_widget = "ANIM_GGT_pegs_transform_widget"
    bl_context_mode = "PAINT_GPENCIL"
    bl_icon = "ops.generic.select"

    @staticmethod
    def draw_settings(
        context, layout: bpy.types.UILayout, tool: bpy.types.WorkSpaceTool
    ):
        ob: bpy.types.Object = context.active_object
        gpd: bpy.types.GreasePencil = ob.data
        armature_object: bpy.types.Object = gpd.pegbar_object
        if not armature_object:
            return

        layout.operator("anim.peg_reset_transform", text="Reset Transformation")


classes = (
    GPENCIL_UL_draw_pegbars,
    GPENCIL_MT_peg_parent,
    VIEW3D_PT_pegbar_system,
    PegsTransformWidgetGroup,
)


def register():
    register_classes(classes)

    bpy.utils.register_tool(PegsTransformTool, after="builtin.transform")


def unregister():
    unregister_classes(classes)

    bpy.utils.unregister_tool(PegsTransformTool)
