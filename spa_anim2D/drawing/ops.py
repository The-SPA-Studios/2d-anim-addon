# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from bisect import bisect

import bpy
import bpy_extras.view3d_utils
import bgl
import gpu
import gpu_extras.presets
import mathutils

from spa_anim2D.drawing.core import (
    clear_parent,
    create_gpencil_object,
    is_parented_to,
    orient_to_view,
    set_parent,
    refresh_quick_edit_gizmo,
)

from spa_anim2D.gpu_utils import OverlayDrawer, ui_scaled
from spa_anim2D.utils import register_classes, unregister_classes


# Custom Blender build compatibility helper functions


def view3d_supports_roll(region_3d: bpy.types.RegionView3D) -> bool:
    """Whether 3D view supports roll."""
    return hasattr(region_3d, "view_roll_angle")


def view3d_is_rolled(region_3d: bpy.types.RegionView3D):
    """Whether 3D view has a non-zero roll value."""
    return getattr(region_3d, "view_roll_angle", 0) != 0


def view3d_supports_mirroring(region_3d: bpy.types.RegionView3D) -> bool:
    """Whether 3D view supports mirroring."""
    return hasattr(region_3d, "view_mirror_x")


def view3d_is_mirrored(region_3d: bpy.types.RegionView3D) -> bool:
    """Whether view is mirrored."""
    return getattr(region_3d, "view_mirror_x", False)


class OBJECT_OT_grease_pencil_transfer_mode(bpy.types.Macro):
    """
    This macro combines object.transfer_mode and a msgbus notification to reflect
    active object change.
    """

    bl_idname = "object.gp_mode_transfer"
    bl_label = "GP Transfer Mode"
    bl_keymaps = [
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "LEFTMOUSE",
            "ctrl": True,
            "shift": True,
            "value": "CLICK",
        }
    ]


class MSGBUS_OT_layer_objects_active(bpy.types.Operator):
    bl_idname = "msgbus.layer_objects_active"
    bl_label = "Publish RNA: LayerObjects Active"
    bl_options = {"INTERNAL"}

    def execute(self, context: bpy.types.Context):
        # Publish msgbus event to indicate active object change
        # (not done by object.mode_transfer operator).
        # This allows for other components relying on this to update correctly.
        bpy.msgbus.publish_rna(key=(bpy.types.LayerObjects, "active"))
        return {"FINISHED"}


class OBJECT_OT_drawing_add(bpy.types.Operator):
    bl_idname = "object.drawing_add"
    bl_label = "New Drawing Object"
    bl_description = "Add a new Grease Pencil object setup for drawing"
    bl_options = {"UNDO"}
    bl_property = "name"

    name: bpy.props.StringProperty(
        name="Name",
        description="Object name",
        options={"SKIP_SAVE"},
    )

    location_mode: bpy.props.EnumProperty(
        name="Location",
        items=(
            ("CURSOR", "3D Cursor", "", "PIVOT_CURSOR", 0),
            ("VIEW", "View Offset", "", "CON_TRACKTO", 1),
        ),
        default="VIEW",
    )

    view_offset: bpy.props.FloatProperty(
        name="View Offset",
        description="Offset from current view",
        default=6.0,
        step=1.0,
        min=0.5,
        subtype="DISTANCE",
    )

    view_orient_x: bpy.props.BoolProperty(
        name="Orient to View on X",
        default=True,
    )

    view_orient_y: bpy.props.BoolProperty(
        name="Orient to View on Y",
        default=True,
    )

    view_orient_z: bpy.props.BoolProperty(
        name="Orient to View on Z",
        default=True,
    )

    pin_to_camera: bpy.props.BoolProperty(
        name="Pin To Camera", description="Pin new drawing to active camera"
    )

    def draw(self, context: bpy.types.Context):
        self.layout.use_property_split = True
        self.layout.prop(self, "name")
        self.layout.prop(self, "location_mode")
        if self.location_mode == "VIEW":
            row = self.layout.row(align=True)
            row.prop(self, "view_offset")
            sub_row = row.row()
            sub_row.enabled = (
                context.area.spaces.active.region_3d.view_perspective == "CAMERA"
            )
            sub_row.prop(self, "pin_to_camera", icon="CON_CAMERASOLVER", text="")
        row = self.layout.row(align=True, heading="Orient Axis")
        row.prop(self, "view_orient_x", text="X", toggle=True)
        row.prop(self, "view_orient_y", text="Y", toggle=True)
        row.prop(self, "view_orient_z", text="Z", toggle=True)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        if not context.area.spaces.active.region_3d.view_perspective == "CAMERA":
            # Disable camera pinning if outside camera view
            self.pin_to_camera = False
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context):
        obj = create_gpencil_object(context, self.name)
        view_matrix = context.area.spaces.active.region_3d.view_matrix

        if self.location_mode == "CURSOR":
            obj.location = context.scene.cursor.location.copy()
        else:
            cam_matrix = view_matrix.inverted()
            obj.location = cam_matrix @ mathutils.Vector((0, 0, -self.view_offset))
            if self.pin_to_camera:
                set_parent(obj, context.scene.camera, use_contraint=True)
        orient_axis = (self.view_orient_x, self.view_orient_y, self.view_orient_z)
        if any(orient_axis):
            orient_to_view(obj, view_matrix, orient_axis)

        return {"FINISHED"}


class OBJECT_OT_pin_to_camera(bpy.types.Operator):
    bl_idname = "object.pin_to_camera"
    bl_label = "Pin object to camera"
    bl_description = "Attach object to the active camera"
    bl_options = {"UNDO"}

    toggle: bpy.props.BoolProperty(
        name="Toggle",
        description="Unpin object if already attached to camera",
        default=True,
    )

    @classmethod
    def poll(self, context: bpy.types.Context):
        return context.active_object and context.scene.camera

    def execute(self, context: bpy.types.Context):
        obj = context.active_object
        camera = context.scene.camera

        if is_parented_to(obj, camera):
            if self.toggle:
                clear_parent(obj, camera)
            else:
                return {"CANCELLED"}
        else:
            set_parent(obj, camera, use_contraint=True)

        return {"FINISHED"}


class OBJECT_OT_orient_to_view(bpy.types.Operator):
    bl_idname = "object.orient_to_view"
    bl_label = "Orient Object to View"
    bl_description = "Rotate object to face active view"
    bl_options = {"UNDO"}

    @classmethod
    def poll(self, context: bpy.types.Context):
        return context.active_object is not None

    def execute(self, context: bpy.types.Context):
        view_matrix = context.area.spaces.active.region_3d.view_matrix
        orient_to_view(context.active_object, view_matrix)
        return {"FINISHED"}


def quick_edit_poll(context: bpy.types.Context) -> bool:
    """Generic poll function for quick-edit related operators."""
    if not getattr(context.active_object, "type", None) == "GPENCIL":
        return False
    if not isinstance(context.region.data, bpy.types.RegionView3D):
        return False
    # Only enable this operator when using the quick edit tool in paint mode.
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    return (
        tool is not None
        and tool.mode == "PAINT_GPENCIL"
        and tool.widget == "VIEW3D_GGT_gpencil_xform_box"
    )


def calculate_move_vector(
    obj: bpy.types.Object, region: bpy.types.Region, axis: tuple[int, int], step: int
) -> mathutils.Vector:
    """
    This function calculates a vector pointing along `axis` scaled to the current
    pixel size in the viewport (at the distance to the object origin).
    """
    rv3d: bpy.types.RegionView3D = region.data
    obj_loc = obj.matrix_world.to_translation().to_3d()

    # Compute pixel size at object's origin.
    p_start = bpy_extras.view3d_utils.region_2d_to_location_3d(
        region, rv3d, (0, 0), obj_loc
    )
    p_end = bpy_extras.view3d_utils.region_2d_to_location_3d(
        region, rv3d, axis, obj_loc
    )
    p_vec = p_end - p_start
    pixel_size = p_vec.length * step

    # TODO: Make this dependent on current drawing plane.
    # Front plane of the grease pencil object.
    obact_normal = obj.matrix_world @ mathutils.Vector((0, 1, 0))
    # Forward vector of active view.
    forward = rv3d.perspective_matrix.inverted() @ mathutils.Vector((0, 0, -1))

    cam_and_obj_aligned = forward.dot(obact_normal) > 0
    # Invert X axis (flip left/right) if only one of those conditions is met:
    # - view is mirrored
    # - view's forward vector and plane's normal are in the same direction
    flip_x_axis = view3d_is_mirrored(rv3d) != cam_and_obj_aligned
    if flip_x_axis:
        axis[0] *= -1

    # TODO: Make this dependent on current drawing plane.
    move_vec = mathutils.Vector((axis[0], 0, axis[1]))

    return move_vec * pixel_size


class GPENCIL_OT_base_gizmo_move_with_arrow_keys:
    bl_options = {"UNDO"}

    bl_keymaps_defaults = {
        "space_type": "VIEW_3D",
        "category_name": "3D View Generic",
    }

    shift_step = 5

    bl_keymaps = [
        {"key": "UP_ARROW", "ctrl": True, "properties": {"axis": (0, 1)}},
        {
            "key": "UP_ARROW",
            "ctrl": True,
            "shift": True,
            "properties": {"axis": (0, 1), "step": shift_step},
        },
        {"key": "RIGHT_ARROW", "ctrl": True, "properties": {"axis": (1, 0)}},
        {
            "key": "RIGHT_ARROW",
            "ctrl": True,
            "shift": True,
            "properties": {"axis": (1, 0), "step": shift_step},
        },
        {"key": "DOWN_ARROW", "ctrl": True, "properties": {"axis": (0, -1)}},
        {
            "key": "DOWN_ARROW",
            "ctrl": True,
            "shift": True,
            "properties": {"axis": (0, -1), "step": shift_step},
        },
        {"key": "LEFT_ARROW", "ctrl": True, "properties": {"axis": (-1, 0)}},
        {
            "key": "LEFT_ARROW",
            "ctrl": True,
            "shift": True,
            "properties": {"axis": (-1, 0), "step": shift_step},
        },
    ]

    axis: bpy.props.IntVectorProperty(
        name="Axis",
        description="Axis to move",
        size=2,
        default=(0, 0),
        options={"SKIP_SAVE"},
    )

    step: bpy.props.IntProperty(
        name="Pixel Step",
        description="Move step in pixels",
        default=1,
        options={"SKIP_SAVE"},
    )


class GPENCIL_OT_quick_edit_strokes_move(
    GPENCIL_OT_base_gizmo_move_with_arrow_keys, bpy.types.Operator
):
    bl_idname = "gpencil.quick_edit_strokes_move"
    bl_label = "Move Grease Pencil Strokes"
    bl_description = "Move selected Grease Pencil strokes in quick edit tool"

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return quick_edit_poll(context)

    def execute(self, context: bpy.types.Context):
        # Calculate the vector to move the strokes in
        move_vec = calculate_move_vector(
            context.active_object, context.region, self.axis, self.step
        )

        # Move selected strokes.
        res = bpy.ops.transform.transform(
            mode="TRANSLATION",
            value=move_vec.to_4d(),
            orient_type="LOCAL",
            gpencil_strokes=True,
        )

        # Cancel operator if no strokes were moved.
        if res != {"FINISHED"}:
            return {"CANCELLED"}

        # Re-set the tool to update quick edit gizmo.
        # TODO: Find a better solution for this.
        bpy.ops.wm.tool_set_by_id(name="builtin.select_lasso")

        return {"FINISHED"}


class GPENCIL_OT_quick_edit_strokes_duplicate(bpy.types.Operator):
    bl_idname = "gpencil.quick_edit_strokes_duplicate"
    bl_label = "Duplicate and Move Strokes"
    bl_description = (
        "Duplicate and move selected Grease Pencil strokes in quick edit tool"
    )
    bl_options = {"UNDO"}

    bl_keymaps = [
        {
            "space_type": "VIEW_3D",
            "category_name": "3D View Generic",
            "key": "D",
            "shift": True,
        }
    ]

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return quick_edit_poll(context)

    def invoke(self, context, event):
        # Duplicate stroke selection first.
        try:
            # Handle runtime errors of duplicate operator
            # (e.g: does not work in multiframe edit).
            bpy.ops.gpencil.duplicate()
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        # Start modal translation.
        bpy.ops.transform.transform(
            "INVOKE_DEFAULT",
            mode="TRANSLATION",
            # For now, lock on front plane (XZ) axis.
            constraint_axis=(True, False, True),
            orient_type="LOCAL",
            gpencil_strokes=True,
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        # Confirm translation.
        if event.type in {"LEFTMOUSE", "ENTER"} and event.value in {"RELEASE"}:
            # Force quick edit gizmo display update.
            bpy.ops.wm.tool_set_by_id(name="builtin.select_lasso")
            return {"FINISHED"}
        # Cancel translation (strokes are still duplicated).
        elif event.type in {"RIGHTMOUSE", "ESC"} and event.value in {"RELEASE"}:
            return {"FINISHED"}
        # When running modally, this operator is a no-op.
        return {"PASS_THROUGH"}


def shift_and_trace_poll(context: bpy.types.Context) -> bool:
    """Generic poll function for shift-and-trace related operators."""
    if not getattr(context.active_object, "type", None) == "GPENCIL":
        return False
    if not isinstance(context.region.data, bpy.types.RegionView3D):
        return False
    # Only enable this operator when using the shift and trace tool in paint mode.
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    return (
        tool is not None
        and tool.mode == "PAINT_GPENCIL"
        and tool.widget == "VIEW3D_GGT_gpencil_frame_offset"
    )


class GPENCIL_OT_shift_and_trace_frame_move(
    GPENCIL_OT_base_gizmo_move_with_arrow_keys, bpy.types.Operator
):
    bl_idname = "gpencil.shift_and_trace_frame_move"
    bl_label = "Move shifted frame"
    bl_description = "Move frame in shift and trace tool"

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return shift_and_trace_poll(context)

    def execute(self, context: bpy.types.Context):
        gpd: bpy.types.GreasePencil = context.active_object.data
        frame_offset_settings = context.tool_settings.gpencil_frame_offset
        use_current_frame = frame_offset_settings.use_current_frame

        # FIXME: The mode should be stored on the frame_offset_settings
        # mode = frame_offset_settings.mode
        mode = "ACTIVE"

        frame = None
        if mode == "ACTIVE":
            if len(gpd.layers.active.frames) == 0:
                return {"CANCELLED"}

            if use_current_frame:
                frame = gpd.layers.active.active_frame
            else:
                idx = max(
                    bisect(
                        gpd.layers.active.frames,
                        frame_offset_settings.frame,
                        key=lambda x: x.frame_number,
                    )
                    - 1,
                    0,
                )
                frame = gpd.layers.active.frames[idx]
        else:
            pass

        if not frame:
            return {"CANCELLED"}

        # Calculate the vector to move the strokes in
        move_vec = calculate_move_vector(
            context.active_object, context.region, self.axis, self.step
        )

        # FIXME: Changing the translation of the frame should update the matrix so we don't have to do this here
        frame.offset = frame.offset @ mathutils.Matrix.Translation(move_vec.to_4d())

        # Project move_vec onto transform plane and shift transform value
        # FIXME: This needs to not be hardcoded
        move_vec = move_vec @ mathutils.Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))

        frame.translation[0] += move_vec[0]
        frame.translation[1] += move_vec[1]
        return {"FINISHED"}


class VIEW3D_OT_view_roll_2d(bpy.types.Operator):
    bl_idname = "view3d.view_roll_2d"
    bl_label = "View Roll 2D"
    bl_description = "Rotate view in 2D"

    bl_keymaps_defaults = {
        "space_type": "VIEW_3D",
        "category_name": "3D View Generic",
    }
    bl_keymaps = [
        {
            "key": "MIDDLEMOUSE",
            "ctrl": True,
            "shift": True,
            "value": "PRESS",
        }
    ]

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return isinstance(
            context.region_data, bpy.types.RegionView3D
        ) and view3d_supports_roll(context.region_data)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self.center = (
            mathutils.Vector((context.region.width, context.region.height)) / 2
        )
        self.mouse_start = (
            mathutils.Vector((event.mouse_region_x, event.mouse_region_y)) - self.center
        )
        self.rotation_start = context.space_data.region_3d.view_roll_angle

        self.view_cam_offset = mathutils.Vector(
            context.space_data.region_3d.view_camera_offset
        )
        self.ratio = context.region.height / context.region.width
        context.window_manager.modal_handler_add(self)

        drawer = OverlayDrawer()

        self.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            VIEW3D_OT_view_roll_2d.draw_rotate_overlay,
            (context, context.region, drawer),
            "WINDOW",
            "POST_PIXEL",
        )

        return {"RUNNING_MODAL"}

    def set_cam_view_offset_from_angle(self, context, angle):
        """apply inverse of the rotation on view offset in cam rotate from view center"""

    def update_view_roll(self, context: bpy.types.Context, delta_angle: float):
        region_3d = context.space_data.region_3d
        region_3d.view_roll_angle = self.rotation_start + delta_angle

        rot_mat2d = mathutils.Matrix.Rotation(delta_angle, 2)

        cam_offset = self.view_cam_offset.copy()

        view3d_mirrored = view3d_is_mirrored(region_3d)

        cam_offset.y *= self.ratio
        if view3d_mirrored:
            cam_offset.x *= -1
        cam_offset.rotate(rot_mat2d)
        if view3d_mirrored:
            cam_offset.x *= -1
        cam_offset.y /= self.ratio

        region_3d.view_camera_offset = cam_offset

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        status = "RUNNING_MODAL"
        if event.type in {"MOUSEMOVE"}:
            mouse_current = (
                mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
                - self.center
            )
            delta_angle = mouse_current.angle_signed(self.mouse_start)
            if view3d_is_mirrored(context.region_data):
                delta_angle *= -1
            self.update_view_roll(context, delta_angle)

        elif event.type in {"LEFTMOUSE", "MIDDLEMOUSE"} and event.value == "RELEASE":
            status = "FINISHED"
        elif event.type in {"RIGHTMOUSE", "ESC"}:
            context.space_data.region_3d.view_roll_angle = 0
            status = "CANCELLED"

        if status != "RUNNING_MODAL":
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle, "WINDOW")
            # Force redraw to avoid having the overlay displayed after this point.
            context.region.tag_redraw()

        return {status}

    @staticmethod
    def draw_rotate_overlay(
        context: bpy.types.Context, region: bpy.types.Region, drawer: OverlayDrawer
    ):
        # Only display overlay in the region running the operator.
        if bpy.context.region != region:
            return

        angle = context.space_data.region_3d.view_roll_angle
        center = (region.width / 2.0, region.height / 2.0)
        radius = min(region.width * 0.6 / 2.0, region.height * 0.6 / 2.0)
        ratio = context.scene.render.resolution_y / context.scene.render.resolution_x
        up_tick_length = radius * 0.1
        center_col = (0.2, 0.2, 0.2, 0.8)
        main_col = (0.15, 0.56, 1.0, 0.9)

        # Center of rotation.
        bgl.glLineWidth(1)
        gpu_extras.presets.draw_circle_2d(center, center_col, 3, segments=16)

        # Main circle.
        bgl.glLineWidth(3)
        gpu_extras.presets.draw_circle_2d(center, main_col, radius, segments=64)

        with gpu.matrix.push_pop():
            gpu.matrix.translate(center)
            if view3d_is_mirrored(region.data):
                gpu.matrix.scale([-1, 1])
            gpu.matrix.multiply_matrix(mathutils.Matrix.Rotation(angle, 4, (0, 0, 1)))
            # Up tick.
            drawer.draw_lines([[0, radius - up_tick_length], [0, radius]], main_col)
            # Frame box.
            drawer.draw_box(
                -radius, -radius * ratio, radius * 2, (radius * ratio * 2), main_col
            )

    def execute(self, context: bpy.types.Context):
        return {"FINISHED"}


class VIEW3D_OT_view_roll_2d_reset(bpy.types.Operator):
    bl_idname = "view3d.view_roll_2d_reset"
    bl_label = "Reset View Roll"
    bl_description = "Reset view roll"

    bl_keymaps_defaults = {
        "space_type": "VIEW_3D",
        "category_name": "3D View Generic",
    }
    bl_keymaps = [
        {
            "key": "R",
            "ctrl": True,
            "shift": True,
            "value": "PRESS",
        }
    ]

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return isinstance(
            context.region_data, bpy.types.RegionView3D
        ) and view3d_is_rolled(context.region_data)

    def execute(self, context):
        region_3d = context.space_data.region_3d
        rot_mat2d = mathutils.Matrix.Rotation(-region_3d.view_roll_angle, 2)
        ratio = context.region.height / context.region.width

        cam_offset = mathutils.Vector(region_3d.view_camera_offset)
        cam_offset.y *= ratio
        cam_offset.rotate(rot_mat2d)
        cam_offset.y /= ratio

        region_3d.view_camera_offset = cam_offset
        region_3d.view_roll_angle = 0

        return {"FINISHED"}


class VIEW3D_OT_view_mirror(bpy.types.Operator):
    bl_idname = "view3d.view_mirror"
    bl_label = "Toggle View Mirror"
    bl_description = "Toggle view mirror"

    bl_keymaps_defaults = {
        "space_type": "VIEW_3D",
        "category_name": "3D View Generic",
    }
    bl_keymaps = [
        {
            "key": "W",
            "shift": True,
            "value": "PRESS",
            "properties": {
                "action": "TOGGLE",
            },
        }
    ]

    action: bpy.props.EnumProperty(
        items=(
            ("ENABLE", "Enable", ""),
            ("DISABLE", "Disable", ""),
            ("TOGGLE", "Toggle", ""),
        ),
        default="TOGGLE",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return isinstance(
            context.region_data, bpy.types.RegionView3D
        ) and view3d_supports_mirroring(context.region_data)

    def execute(self, context):
        region_3d = context.region_data
        is_view_mirrored = view3d_is_mirrored(region_3d)
        do_mirror = self.action == "ENABLE" or (
            self.action == "TOGGLE" and not is_view_mirrored
        )

        if is_view_mirrored == do_mirror:
            return {"CANCELLED"}

        # Flip X view offset.
        region_3d.view_camera_offset[0] *= -1
        region_3d.view_mirror_x = do_mirror

        return {"FINISHED"}


class VIEW3D_GGT_view_roll_2d(bpy.types.GizmoGroup):
    bl_label = "View Roll Gizmos"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        return getattr(context.space_data.region_3d, "view_roll_angle", 0) != 0

    def draw_prepare(self, context: bpy.types.Context):
        if not self.gizmos:
            return

        region = context.region
        self.gizmo.matrix_basis[0][3] = region.width / 2
        self.gizmo.matrix_basis[1][3] = ui_scaled(24)

    def add_gizmo(self, operator: str):
        gizmo = self.gizmos.new("GIZMO_GT_button_2d")
        gizmo.draw_options = {"BACKDROP", "OUTLINE"}
        gizmo.color = 0.1, 0.1, 0.1
        gizmo.color_highlight = 0.4, 0.4, 0.4
        gizmo.alpha = gizmo.alpha_highlight = 0.6
        gizmo.scale_basis = ui_scaled(14)
        gizmo.show_drag = False
        props = gizmo.target_set_operator(operator)
        return gizmo, props

    def setup(self, context):
        self.gizmo, _ = self.add_gizmo("view3d.view_roll_2d_reset")
        self.gizmo.icon = "FILE_REFRESH"
        self.gizmo.color = 0.15, 0.56, 1.0
        self.gizmo.color_highlight = 0.15, 0.56, 1.0


class GPENCIL_OT_mirror_strokes(bpy.types.Operator):
    bl_idname = "gpencil.mirror_strokes"
    bl_label = "Mirror"
    bl_description = "Mirror the selected strokes"

    axis: bpy.props.StringProperty(name="axis", default="X")

    @classmethod
    def poll(cls, context: bpy.types.Context):
        if not getattr(context.active_object, "type", None) == "GPENCIL":
            return False
        if not isinstance(context.region.data, bpy.types.RegionView3D):
            return False
        return True

    def execute(self, context: bpy.types.Context):
        previous_pivot = context.tool_settings.transform_pivot_point
        context.tool_settings.transform_pivot_point = "BOUNDING_BOX_CENTER"

        constraint_axis = (
            (True, False, False) if self.axis == "X" else (False, False, True)
        )

        bpy.ops.transform.mirror(
            orient_type="LOCAL",
            constraint_axis=constraint_axis,
            gpencil_strokes=True,
        )
        context.tool_settings.transform_pivot_point = previous_pivot

        refresh_quick_edit_gizmo(context)

        return {"FINISHED"}


classes = (
    MSGBUS_OT_layer_objects_active,
    OBJECT_OT_grease_pencil_transfer_mode,
    OBJECT_OT_drawing_add,
    OBJECT_OT_pin_to_camera,
    OBJECT_OT_orient_to_view,
    GPENCIL_OT_quick_edit_strokes_move,
    GPENCIL_OT_quick_edit_strokes_duplicate,
    GPENCIL_OT_shift_and_trace_frame_move,
    VIEW3D_OT_view_roll_2d,
    VIEW3D_OT_view_roll_2d_reset,
    VIEW3D_OT_view_mirror,
    VIEW3D_GGT_view_roll_2d,
    GPENCIL_OT_mirror_strokes,
)


def register():
    register_classes(classes)

    OBJECT_OT_grease_pencil_transfer_mode.define("OBJECT_OT_transfer_mode")
    OBJECT_OT_grease_pencil_transfer_mode.define("MSGBUS_OT_layer_objects_active")


def unregister():
    unregister_classes(classes)
