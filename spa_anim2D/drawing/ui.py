# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy
from spa_anim2D.animation.pegs.core import get_bones_from_peg_bone_group

from spa_anim2D.drawing.core import get_active_gp_object, is_parented_to
from spa_anim2D.drawing.ops import (
    view3d_is_rolled,
    view3d_is_mirrored,
    view3d_supports_mirroring,
    view3d_supports_roll,
)
from spa_anim2D.utils import register_classes, unregister_classes
from spa_anim2D.keymaps import register_keymap


class SCENE_UL_gpencil_objects(bpy.types.UIList):
    """
    Template to display the grease pencil objects of a scene.
    """

    bl_idname = "SCENE_UL_gpencil"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname
    ):
        layout.prop(item, "name", text="", emboss=False)
        camera_pin_icon = (
            "CON_CAMERASOLVER"
            if is_parented_to(item, context.scene.camera)
            else "BLANK1"
        )
        layout.label(icon=camera_pin_icon, text="")
        # FIXME: https://developer.blender.org/T100203
        # if get_addon_prefs().drawings_show_depth:
        #     layout.prop(item, "camera_view_depth", text="")

        layout.prop(item, "show_in_front", text="", icon="AXIS_FRONT")

    def filter_item_flag(self, obj):
        """Filter function defining whether an item should be displayed in the list."""
        if (
            isinstance(obj.data, bpy.types.GreasePencil)
            and self.filter_name.strip().lower() in obj.name.lower()
        ):
            return self.bitflag_filter_item
        return 0

    def filter_items(self, context: bpy.types.Context, obj, propname):
        objects = getattr(obj, propname)

        flt_neworder = []

        flt_flags = [self.filter_item_flag(obj) for obj in objects]

        return flt_flags, flt_neworder

    def draw_filter(self, context, layout):
        row = layout.row()

        subrow = row.row(align=True)
        subrow.prop(self, "filter_name", text="")

        # FIXME: https://developer.blender.org/T100203
        # subrow = row.row(align=True)
        # subrow.prop(
        #     get_addon_prefs(), "drawings_show_depth", icon="MOD_LENGTH", icon_only=True
        # )


class GPENCIL_MT_layer_peg_link_select(bpy.types.Menu):
    bl_idname = "GPENCIL_MT_layer_peg_link_select"
    bl_label = "Peg"
    bl_description = "Select active layer peg link"

    def draw(self, context):
        obj = get_active_gp_object()
        if not obj:
            return

        gpd = obj.data
        if not gpd.pegbar_object:
            return

        armature_object: bpy.types.Object = gpd.pegbar_object

        # First entry is there to unlink the peg.
        self.layout.operator("anim.peg_parent_active_layer", text=" - ").unparent = True

        # Iterate through all the bones and create entries for them. Highlight the currently linked peg (if there is one).
        for bone_group in armature_object.pose.bone_groups:
            _, offset = get_bones_from_peg_bone_group(armature_object, bone_group)
            icon = (
                "STATUSBAR" if offset.name == gpd.layers.active.parent_bone else "NONE"
            )
            self.layout.operator(
                "anim.peg_parent_active_layer", text=bone_group.name, icon=icon
            ).peg_name = bone_group.name


class GPENCIL_UL_draw_layer(bpy.types.UIList):
    """
    Template to display the layers of a grease pencil object.
    """

    bl_idname = "GPENCIL_UL_draw_layer"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname
    ):
        armature_object: bpy.types.Object = data.pegbar_object
        pose_bone = (
            armature_object.pose.bones.get(item.parent_bone)
            if armature_object
            else None
        )

        # Layer name
        layout.prop(item, "info", text="", emboss=False)

        # Peg name
        icon = "NONE" if item.parent_bone == "" else "STATUSBAR"
        layout.label(text=pose_bone.bone_group.name if pose_bone else "", icon=icon)

        # Layer properties
        sub = layout.row(align=True)
        # - Opacity
        sub.prop(item, "opacity", text="", slider=True, emboss=True)
        sub.separator()
        # - Onion skinning
        onion_icon = "ONIONSKIN_ON" if item.use_onion_skinning else "ONIONSKIN_OFF"
        sub.prop(item, "use_onion_skinning", text="", icon=onion_icon, emboss=False)
        # - Visility / Lock
        sub.prop(item, "hide", text="", emboss=False)
        sub.prop(item, "lock", text="", emboss=False)


class VIEW3D_PT_draw_panel(bpy.types.Panel):
    bl_label = "Drawings"
    bl_category = "SPA.Anim2D"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw_header_preset(self, context: bpy.types.Context):
        region_3d = context.space_data.region_3d

        row = self.layout.row(align=True)
        if view3d_supports_mirroring(region_3d):
            row.alert = view3d_is_mirrored(region_3d)
            row.operator(
                "view3d.view_mirror",
                icon="MOD_MIRROR",
                text="",
            )
            row.alert = False
            row.separator()

        if view3d_supports_roll(region_3d):
            row.operator(
                "view3d.view_roll_2d_reset",
                icon="FILE_REFRESH",
                text="",
                depress=view3d_is_rolled(region_3d),
            )

    def draw(self, context: bpy.types.Context):
        row = self.layout.row()

        active_gp = get_active_gp_object()
        sub_row = row.row()
        sub_row.enabled = bool(active_gp)

        # Paint mode toggle button (or placeholder if no active GP object)
        props = sub_row.operator(
            "object.mode_set",
            icon="GREASEPENCIL" if active_gp else "NONE",
            text="Draw" if active_gp else "Select a Grease Pencil Object",
            depress=bool(active_gp) and active_gp.mode == "PAINT_GPENCIL",
        )
        if active_gp:
            props.mode = "PAINT_GPENCIL"
            props.toggle = True

        # Add drawing operator
        row.operator("object.drawing_add", icon="PLUS", text="")

        # Grease pencil grid overlay
        row.prop(
            context.area.spaces.active.overlay,
            "use_gpencil_grid",
            icon="VIEW_ORTHO",
            text="",
        )

        # List of grease pencil objects in the scene
        row = self.layout.row()
        row.template_list(
            SCENE_UL_gpencil_objects.bl_idname,
            "",
            context.scene,
            "objects",
            context.scene,
            "active_gp_index",
            type="DEFAULT",
            columns=2,
            rows=2,
        )

        # Toolbar
        col = row.column()
        col.enabled = bool(active_gp)

        col.operator(
            "object.pin_to_camera",
            icon="CON_CAMERASOLVER",
            text="",
            depress=is_parented_to(context.active_object, context.scene.camera),
        )

        col.operator(
            "object.orient_to_view",
            icon="ORIENTATION_NORMAL",
            text="",
        )

        if not active_gp:
            return

        # Active GP object layers list and tools
        row = self.layout.row()

        row.template_list(
            GPENCIL_UL_draw_layer.bl_idname,
            "",
            active_gp.data,
            "layers",
            active_gp.data.layers,
            "active_index",
            type="DEFAULT",
            columns=2,
            rows=3,
            sort_reverse=True,
            sort_lock=True,
        )

        col = row.column(align=True)
        col.operator("gpencil.layer_add", icon="ADD", text="")
        col.operator("gpencil.layer_remove", icon="REMOVE", text="")
        col.separator()
        col.operator("gpencil.layer_move", icon="TRIA_UP", text="").type = "UP"
        col.operator("gpencil.layer_move", icon="TRIA_DOWN", text="").type = "DOWN"

        if gpl := active_gp.data.layers.active:
            self.draw_gpencil_layer_peg_ui(self.layout, gpl)

    def draw_gpencil_layer_peg_ui(
        self, layout: bpy.types.UILayout, gpl: bpy.types.GPencilLayer
    ):
        """Draw grease pencil layer peg selection UI."""
        row = layout.row(heading="Peg")

        active_gp = get_active_gp_object()
        armature_object: bpy.types.Object = active_gp.data.pegbar_object
        pose_bone = (
            armature_object.pose.bones.get(active_gp.data.layers.active.parent_bone)
            if armature_object
            else None
        )
        text = pose_bone.bone_group.name if pose_bone else "None"
        icon = "STATUSBAR" if pose_bone else "NONE"
        row.menu(
            GPENCIL_MT_layer_peg_link_select.bl_idname,
            text=text,
            icon=icon,
        )
        row.operator("anim.peg_bake_active_layer", text="Bake", icon="IMPORT")


class GPENCIL_MT_drawing_add(bpy.types.Menu):
    bl_idname = "GPENCIL_MT_drawing_add"
    bl_label = "Add"
    bl_description = ""

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return context.mode == "PAINT_GPENCIL"

    def draw(self, context):
        layout = self.layout

        layout.operator_context = "INVOKE_DEFAULT"
        layout.operator(
            "import.gpencil_references_from_file",
            text="Reference(s) from file...",
            icon="IMAGE_DATA",
        )


def draw_quick_edit_header(self, context: bpy.types.Context):
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if (
        tool is not None
        and tool.mode == "PAINT_GPENCIL"
        and tool.widget == "VIEW3D_GGT_gpencil_xform_box"
    ):
        row = self.layout.row(align=True)
        row.label(text="Mirror: ")
        row.operator("gpencil.mirror_strokes", text="X").axis = "X"
        row.operator("gpencil.mirror_strokes", text="Y").axis = "Y"


classes = (
    SCENE_UL_gpencil_objects,
    VIEW3D_PT_draw_panel,
    GPENCIL_UL_draw_layer,
    GPENCIL_MT_drawing_add,
    GPENCIL_MT_layer_peg_link_select,
)


def register():
    register_classes(classes)

    register_keymap(
        "wm.call_menu", "A", shift=True, properties={"name": "GPENCIL_MT_drawing_add"}
    )

    bpy.types.VIEW3D_HT_tool_header.prepend(draw_quick_edit_header)


def unregister():
    unregister_classes(classes)

    bpy.types.VIEW3D_HT_tool_header.remove(draw_quick_edit_header)
