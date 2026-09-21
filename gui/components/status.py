"""Activity log: a read-only, append-only history of user-visible actions.

Presentation restyled for the warm-light theme; append behaviour unchanged.
"""

import tkinter as tk

from ..theme import OrynTheme


class ActivityLog(tk.Text):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            wrap=tk.WORD,
            # CHANGED: light theme colors.
            bg=OrynTheme.color("surface_alt"),
            fg=OrynTheme.color("text"),
            insertbackground=OrynTheme.color("text"),
            selectbackground=OrynTheme.color("selection"),
            selectforeground=OrynTheme.color("selected_text"),
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=OrynTheme.color("border"),
            highlightcolor=OrynTheme.color("border_strong"),
            padx=14,
            pady=10,
            font=OrynTheme.font("mono"),
            **kwargs,
        )
        self.config(state=tk.DISABLED)

    def append(self, message):
        self.config(state=tk.NORMAL)
        self.insert(tk.END, f"{message}\n")
        self.see(tk.END)
        self.config(state=tk.DISABLED)


__all__ = ["ActivityLog"]
