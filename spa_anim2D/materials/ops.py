# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

import bpy

from spa_anim2D.materials.core import refresh_palettes
from spa_anim2D.utils import register_classes, unregister_classes


class MATERIAL_OT_palettes_refresh(bpy.types.Operator):
    bl_idname = "material.palettes_refresh"
    bl_label = "Refresh Material Palettes"
    bl_description = "Refresh material palettes"
    bl_options = set()

    def execute(self, context: bpy.types.Context):
        refresh_palettes(cleanup_materials=True)
        return {"FINISHED"}


classes = (MATERIAL_OT_palettes_refresh,)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
