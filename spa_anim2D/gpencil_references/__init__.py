# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from spa_anim2D.gpencil_references import ops

import bpy

# For the operators to work, we need the `use_automatic_uvs` property on strokes (introduced in spa-studios-v2.1.0).
CHECK = "use_automatic_uvs" in bpy.types.GPencilStroke.bl_rna.properties


def register():
    if CHECK:
        ops.register()


def unregister():
    if CHECK:
        ops.unregister()
