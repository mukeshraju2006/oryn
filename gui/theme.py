"""Oryn visual system.

A warm, light, understated interface: warm ivory surfaces, stone borders,
charcoal typography, muted sage as the working accent and restrained
terracotta for secondary emphasis. Presentation only - no behaviour lives
here.
"""

import tkinter as tk
from tkinter import ttk


class OrynTheme:
    # CHANGED: warm light palette replacing the dark developer theme.
    COLORS = {
        "bg": "#F5F3EE",            # warm ivory, app background
        "bg_alt": "#EFECE5",        # slightly deeper ivory (sidebar, wells)
        "surface": "#FBFAF7",       # card / panel surface
        "surface_alt": "#F3F1EB",   # recessed surface (log, selected rows)
        "border": "#DEDCD5",        # stone hairline
        "border_strong": "#CDCAC1", # slightly firmer hairline
        "text": "#252522",          # charcoal, primary typography
        "text_secondary": "#6E6C64",# muted stone, secondary text
        "text_faint": "#98958B",    # metadata
        "text_on_accent": "#FCFBF8",
        "accent": "#5B6B4F",        # muted sage / olive
        "accent_hover": "#66775A",
        "accent_pressed": "#4F5E45",
        "accent_soft": "#E7E9DF",   # very pale sage wash
        "accent_soft_hover": "#DEE1D4",
        "secondary": "#9C5B40",     # muted terracotta
        "secondary_soft": "#F2E4DC",# pale terracotta wash
        "danger": "#8F3E32",        # terracotta-leaning danger text
        "selection": "#DCE2D2",     # pale sage selection
        "selected_text": "#252522",
    }

    FONTS = {
        "display": ("Segoe UI Semibold", 19),
        "heading": ("Segoe UI Semibold", 12),
        "subheading": ("Segoe UI", 10),
        "body": ("Segoe UI", 9),
        "small": ("Segoe UI", 8),
        "label": ("Segoe UI Semibold", 8),
        "button": ("Segoe UI Semibold", 9),
        "mono": ("Consolas", 9),
    }

    PADDING = {
        "page": 28,
        "card": 18,
        "field": 8,
        "button_x": 18,
        "button_y": 8,
    }

    @classmethod
    def color(cls, name):
        return cls.COLORS.get(name, cls.COLORS["bg"])

    @classmethod
    def font(cls, name):
        return cls.FONTS.get(name, cls.FONTS["body"])

    @classmethod
    def apply(cls, root):
        style = ttk.Style(root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        c = cls.COLORS

        # ---------- frames ----------
        style.configure("Oryn.TFrame", background=c["bg"])
        style.configure("Oryn.Card.TFrame", background=c["surface"])
        style.configure("Oryn.Well.TFrame", background=c["bg_alt"])
        style.configure("Oryn.Sidebar.TFrame", background=c["bg_alt"])

        # ---------- labels ----------
        style.configure(
            "Oryn.TLabel",
            background=c["bg"],
            foreground=c["text"],
            font=cls.FONTS["body"],
        )
        style.configure(
            "Oryn.Display.TLabel",
            background=c["bg"],
            foreground=c["text"],
            font=cls.FONTS["display"],
        )
        style.configure(
            "Oryn.Heading.TLabel",
            background=c["bg"],
            foreground=c["text"],
            font=cls.FONTS["heading"],
        )
        style.configure(
            "Oryn.Secondary.TLabel",
            background=c["bg"],
            foreground=c["text_secondary"],
            font=cls.FONTS["body"],
        )
        style.configure(
            "Oryn.Metadata.TLabel",
            background=c["bg"],
            foreground=c["text_faint"],
            font=cls.FONTS["small"],
        )
        # Small uppercase section label.
        style.configure(
            "Oryn.Section.TLabel",
            background=c["bg"],
            foreground=c["text_faint"],
            font=cls.FONTS["label"],
        )

        # Same label roles on the card surface.
        for base in ("TLabel", "Heading.TLabel", "Secondary.TLabel",
                     "Metadata.TLabel", "Section.TLabel"):
            style.configure(
                "Oryn.Card." + base,
                background=c["surface"],
                foreground=style.lookup("Oryn." + base, "foreground"),
                font=style.lookup("Oryn." + base, "font"),
            )

        # Same label roles on the sidebar / well surface.
        for base in ("TLabel", "Heading.TLabel", "Secondary.TLabel",
                     "Metadata.TLabel", "Section.TLabel"):
            for prefix in ("Oryn.Well", "Oryn.Sidebar"):
                style.configure(
                    prefix + "." + base,
                    background=c["bg_alt"],
                    foreground=style.lookup("Oryn." + base, "foreground"),
                    font=style.lookup("Oryn." + base, "font"),
                )

        # ---------- entries ----------
        style.configure(
            "Oryn.TEntry",
            fieldbackground=c["surface"],
            foreground=c["text"],
            insertcolor=c["text"],
            bordercolor=c["border_strong"],
            lightcolor=c["surface"],
            darkcolor=c["surface"],
            borderwidth=1,
            relief="solid",
            padding=(10, 8),
        )
        style.map(
            "Oryn.TEntry",
            bordercolor=[("focus", c["accent"])],
            lightcolor=[("focus", c["surface"])],
            darkcolor=[("focus", c["surface"])],
        )

        # ---------- combobox ----------
        style.configure(
            "Oryn.TCombobox",
            fieldbackground=c["surface"],
            background=c["surface_alt"],
            foreground=c["text"],
            arrowcolor=c["text_secondary"],
            bordercolor=c["border_strong"],
            lightcolor=c["surface"],
            darkcolor=c["surface"],
            borderwidth=1,
            relief="solid",
            padding=(8, 6),
            arrowsize=13,
        )
        style.map(
            "Oryn.TCombobox",
            fieldbackground=[("readonly", c["surface"])],
            foreground=[("readonly", c["text"])],
            bordercolor=[("focus", c["accent"])],
        )
        # Option list popup.
        root.option_add("*TCombobox*Listbox.background", c["surface"])
        root.option_add("*TCombobox*Listbox.foreground", c["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", c["selection"])
        root.option_add("*TCombobox*Listbox.selectForeground", c["selected_text"])
        root.option_add("*TCombobox*Listbox.font", cls.FONTS["body"])
        root.option_add("*TCombobox*Listbox.borderWidth", 1)

        # ---------- buttons ----------
        # Primary: sage fill, the strongest action (Capture Workspace, Sign in).
        style.configure(
            "Oryn.Primary.TButton",
            background=c["accent"],
            foreground=c["text_on_accent"],
            bordercolor=c["accent"],
            lightcolor=c["accent"],
            darkcolor=c["accent"],
            focuscolor=c["accent"],
            borderwidth=0,
            relief="flat",
            padding=(cls.PADDING["button_x"], cls.PADDING["button_y"]),
            font=cls.FONTS["button"],
        )
        style.map(
            "Oryn.Primary.TButton",
            background=[
                ("disabled", c["accent_soft"]),
                ("pressed", c["accent_pressed"]),
                ("active", c["accent_hover"]),
            ],
            foreground=[
                ("disabled", c["text_faint"]),
                ("active", c["text_on_accent"]),
            ],
            bordercolor=[
                ("disabled", c["accent_soft"]),
                ("pressed", c["accent_pressed"]),
                ("active", c["accent_hover"]),
            ],
        )

        # Secondary: quiet ivory button with a hairline border.
        style.configure(
            "Oryn.TButton",
            background=c["surface"],
            foreground=c["text"],
            bordercolor=c["border_strong"],
            lightcolor=c["surface"],
            darkcolor=c["surface"],
            focuscolor=c["border_strong"],
            borderwidth=1,
            relief="flat",
            padding=(cls.PADDING["button_x"], cls.PADDING["button_y"]),
            font=cls.FONTS["button"],
        )
        style.map(
            "Oryn.TButton",
            background=[
                ("disabled", c["bg_alt"]),
                ("pressed", c["surface_alt"]),
                ("active", c["surface_alt"]),
            ],
            foreground=[
                ("disabled", c["text_faint"]),
                ("active", c["text"]),
            ],
            bordercolor=[
                ("disabled", c["border"]),
                ("active", c["border_strong"]),
            ],
        )

        # Accent-quiet: pale sage wash (Restore Snapshot).
        style.configure(
            "Oryn.AccentQuiet.TButton",
            background=c["accent_soft"],
            foreground=c["accent_pressed"],
            bordercolor=c["accent_soft"],
            lightcolor=c["accent_soft"],
            darkcolor=c["accent_soft"],
            focuscolor=c["accent_soft"],
            borderwidth=0,
            relief="flat",
            padding=(cls.PADDING["button_x"], cls.PADDING["button_y"]),
            font=cls.FONTS["button"],
        )
        style.map(
            "Oryn.AccentQuiet.TButton",
            background=[
                ("disabled", c["bg_alt"]),
                ("pressed", c["accent_soft_hover"]),
                ("active", c["accent_soft_hover"]),
            ],
            foreground=[
                ("disabled", c["text_faint"]),
            ],
        )

        # Terracotta text button (Logout).
        style.configure(
            "Oryn.Terracotta.TButton",
            background=c["bg_alt"],
            foreground=c["secondary"],
            bordercolor=c["bg_alt"],
            lightcolor=c["bg_alt"],
            darkcolor=c["bg_alt"],
            focuscolor=c["bg_alt"],
            borderwidth=0,
            relief="flat",
            padding=(10, 6),
            font=cls.FONTS["small"],
        )
        style.map(
            "Oryn.Terracotta.TButton",
            background=[("active", c["secondary_soft"])],
            foreground=[("active", c["secondary"])],
        )

        # Ghost: flat text button (Refresh, log links).
        style.configure(
            "Oryn.Ghost.TButton",
            background=c["bg"],
            foreground=c["text_secondary"],
            bordercolor=c["bg"],
            lightcolor=c["bg"],
            darkcolor=c["bg"],
            focuscolor=c["bg"],
            borderwidth=0,
            relief="flat",
            padding=(10, 6),
            font=cls.FONTS["small"],
        )
        style.map(
            "Oryn.Ghost.TButton",
            background=[("active", c["surface_alt"])],
            foreground=[("active", c["text"])],
        )

        # ---------- notebook ----------
        style.configure(
            "Oryn.TNotebook",
            background=c["bg"],
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "Oryn.TNotebook.Tab",
            background=c["bg"],
            foreground=c["text_secondary"],
            padding=(14, 8),
            borderwidth=0,
            font=cls.FONTS["button"],
        )
        style.map(
            "Oryn.TNotebook.Tab",
            background=[("active", c["surface_alt"]), ("selected", c["bg"])],
            foreground=[("selected", c["text"])],
        )

        # ---------- scrollbars ----------
        style.configure(
            "Oryn.Vertical.TScrollbar",
            background=c["bg_alt"],
            troughcolor=c["bg"],
            bordercolor=c["bg"],
            arrowcolor=c["text_faint"],
            relief="flat",
        )
        style.map(
            "Oryn.Vertical.TScrollbar",
            background=[("active", c["border_strong"])],
        )
        style.configure(
            "Oryn.Horizontal.TScrollbar",
            background=c["bg_alt"],
            troughcolor=c["bg"],
            bordercolor=c["bg"],
            arrowcolor=c["text_faint"],
            relief="flat",
        )
        style.map(
            "Oryn.Horizontal.TScrollbar",
            background=[("active", c["border_strong"])],
        )

        # ---------- scale (unused today, kept consistent) ----------
        style.configure(
            "Oryn.Horizontal.TScale",
            background=c["bg"],
            troughcolor=c["surface_alt"],
            bordercolor=c["border"],
            lightcolor=c["accent"],
            darkcolor=c["accent"],
        )

        style.configure("Oryn.Status.TLabel", background=c["bg"], foreground=c["text_secondary"], font=cls.FONTS["small"])


def apply_theme(root):
    OrynTheme.apply(root)


__all__ = ["OrynTheme", "apply_theme"]
