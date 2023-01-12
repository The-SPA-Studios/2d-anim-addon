# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2023, The SPA Studios. All rights reserved.

from spa_anim2D.animation import ops, ui, pegs


def register():
    pegs.register()

    ops.register()
    ui.register()


def unregister():
    pegs.unregister()

    ops.unregister()
    ui.unregister()
