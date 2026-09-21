"""Shared presentation helpers: themed buttons, frames, and dividers.

Presentation only. These factories return themed widgets; commands and
behaviour are supplied by the screens.
"""

import tkinter as tk
from tkinter import ttk

from ..theme import OrynTheme


# CHANGED: state-aware primary button (sage fill).
def primary_button(master, text, command=None, **kwargs):
    return ttk.Button(master, text=text, command=command, style="Oryn.Primary.TButton", **kwargs)


# CHANGED: quiet sage-wash button (secondary emphasis).
def secondary_button(master, text, command=None, **kwargs):
    return ttk.Button(master, text=text, command=command, style="Oryn.AccentQuiet.TButton", **kwargs)


# CHANGED: flat low-emphasis text button.
def ghost_button(master, text, command=None, **kwargs):
    return ttk.Button(master, text=text, command=command, style="Oryn.Ghost.TButton", **kwargs)


def card_frame(master, **kwargs):
    return ttk.Frame(master, style="Oryn.Card.TFrame", **kwargs)


def well_frame(master, **kwargs):
    return ttk.Frame(master, style="Oryn.Well.TFrame", **kwargs)


# CHANGED: horizontal hairline divider.
def divider(master, padding_x=0, padding_y=0):
    frame = tk.Frame(
        master,
        height=1,
        bg=OrynTheme.color("border"),
        bd=0,
        highlightthickness=0,
    )
    if padding_x or padding_y:
        frame.pack_configure(fill=tk.X, padx=padding_x, pady=padding_y)
    return frame


# CHANGED: vertical hairline divider (sidebar / content boundary).
def vertical_divider(master):
    return tk.Frame(
        master,
        width=1,
        bg=OrynTheme.color("border"),
        bd=0,
        highlightthickness=0,
    )


__all__ = [
    "primary_button",
    "secondary_button",
    "ghost_button",
    "card_frame",
    "well_frame",
    "divider",
    "vertical_divider",
]
