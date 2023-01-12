# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from spa_anim2D import (
    animation,
    drawing,
    gpencil_references,
    keymaps,
    materials,
    preferences,
)


bl_info = {
    "name": "2D Animation",
    "author": "The SPA Studios",
    "description": "Toolset to improve the 2D animation workflow in Blender.",
    "blender": (3, 3, 0),
    "version": (1, 0, 0),
    "location": "",
    "warning": "",
    "category": "SPA",
}

packages = (
    drawing,
    animation,
    materials,
    gpencil_references,
    preferences,
    keymaps,
)


def register():
    for package in packages:
        package.register()


def unregister():
    for package in packages:
        package.unregister()
