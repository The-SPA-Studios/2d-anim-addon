# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

"""
Addon preferences management.
"""

import bpy

from spa_anim2D.utils import register_classes, unregister_classes


class SPAAnim2DAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    anim_flipping_undo_mode: bpy.props.EnumProperty(
        name="Flipping Undo",
        items=(
            (
                "DEFAULT",
                "Default Behavior",
                "Default Blender undo behavior",
                "LOOP_BACK",
                0,
            ),
            (
                "STICK_TO_FRAME",
                "Stick to Frame",
                "Stay on last edited frame",
                "SNAP_ON",
                1,
            ),
        ),
    )

    drawings_show_depth: bpy.props.BoolProperty(
        name="Show Drawings Depth",
        description="Show drawings depth from active view in Drawings Panel",
        default=False,
    )

    def draw(self, context):

        box = self.layout.box()
        box.label(text="Animation")
        box.prop(self, "anim_flipping_undo_mode")

        # FIXME: https://developer.blender.org/T100203
        # box = self.layout.box()
        # box.label(text="Layout")
        # box.prop(self, "drawings_show_depth")


def get_addon_prefs() -> SPAAnim2DAddonPreferences:
    """Get the Addon Preferences instance."""
    return bpy.context.preferences.addons[__package__].preferences


classes = (SPAAnim2DAddonPreferences,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
