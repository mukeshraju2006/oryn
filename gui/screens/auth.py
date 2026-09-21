import threading
import tkinter as tk
from tkinter import ttk

try:
    from ..cloud.client import CloudClient
    from ..cloud.session import save_token
    from ..components.buttons import divider, primary_button
    from ..components.cards import card_frame
    from ..theme import OrynTheme, apply_theme
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from oryn.cloud.client import CloudClient
    from oryn.cloud.session import save_token
    from gui.components.buttons import divider, primary_button
    from gui.components.cards import card_frame
    from gui.theme import OrynTheme, apply_theme


class AuthScreen(tk.Frame):
    """Login / register screen.

    CHANGED: recomposed from a dark centered card into a calm split layout -
    a quiet ivory introduction panel beside the active form. Callbacks,
    threading and CloudClient usage are unchanged.
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=OrynTheme.color("bg"))
        self.app = app
        self.root = app.root
        self.client = None
        self._build()

    def _build(self):
        apply_theme(self.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self, style="Oryn.TNotebook")
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        self.login_frame = ttk.Frame(self.notebook, style="Oryn.TFrame")
        self.notebook.add(self.login_frame, text="Login")
        self.create_login_widgets()

        self.register_frame = ttk.Frame(self.notebook, style="Oryn.TFrame")
        self.notebook.add(self.register_frame, text="Register")
        self.create_register_widgets()

    def _build_split(self, parent, intro_lines):
        """Shared two-panel composition: intro panel + form column."""
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)

        # Left: quiet ivory introduction panel (full height of the form,
        # sized by its content, column minsize keeps it from collapsing).
        intro = ttk.Frame(parent, style="Oryn.Well.TFrame")
        intro.grid(row=0, column=0, sticky=tk.NSEW)
        parent.columnconfigure(0, weight=0, minsize=280)
        intro.columnconfigure(0, weight=1)

        ttk.Label(intro, text="Oryn", style="Oryn.Well.Heading.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=28, pady=(44, 4)
        )
        ttk.Label(
            intro,
            text="Capture your workspace and restore it wherever you work.",
            style="Oryn.Well.Secondary.TLabel",
            wraplength=200,
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky=tk.EW, padx=28, pady=(0, 18))

        divider(intro).grid(row=2, column=0, sticky=tk.EW, padx=28, pady=(0, 18))

        for i, line in enumerate(intro_lines):
            ttk.Label(
                intro,
                text=line,
                style="Oryn.Well.Metadata.TLabel",
                wraplength=200,
                justify=tk.LEFT,
            ).grid(row=3 + i, column=0, sticky=tk.EW, pady=(0, 8))

        # Right: the form column.
        form = ttk.Frame(parent, style="Oryn.TFrame")
        form.grid(row=0, column=1, sticky=tk.NSEW)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(0, weight=1)

        return form

    def create_login_widgets(self):
        self.login_frame.columnconfigure(0, weight=1)
        self.login_frame.rowconfigure(0, weight=1)

        form = self._build_split(
            self.login_frame,
            [
                "Sign in to reach your saved workspaces on this device.",
                "Captures include VS Code state and browser URLs.",
            ],
        )

        # CHANGED: the form column hugs its content and centers vertically in
        # the row (no N/S sticky) instead of stretching to the window edge.
        card = card_frame(form, padding=(8, 0))
        card.grid(row=0, column=1, sticky=tk.EW, padx=(36, 48))
        card.columnconfigure(0, weight=1)

        inner = ttk.Frame(card, style="Oryn.Card.TFrame")
        inner.pack(fill=tk.BOTH, expand=True)
        inner.columnconfigure(0, weight=1)

        ttk.Label(inner, text="Login", style="Oryn.Card.Heading.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 4)
        )
        ttk.Label(
            inner,
            text="Use your Oryn account credentials.",
            style="Oryn.Card.Metadata.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(0, 26))

        ttk.Label(inner, text="EMAIL", style="Oryn.Card.Section.TLabel").grid(row=2, column=0, sticky=tk.W, pady=(0, 6))
        self.login_email = ttk.Entry(inner, width=36, style="Oryn.TEntry")
        self.login_email.grid(row=3, column=0, sticky=tk.EW, pady=(0, 16))

        ttk.Label(inner, text="PASSWORD", style="Oryn.Card.Section.TLabel").grid(row=4, column=0, sticky=tk.W, pady=(0, 6))
        self.login_password = ttk.Entry(inner, width=36, show="*", style="Oryn.TEntry")
        self.login_password.grid(row=5, column=0, sticky=tk.EW, pady=(0, 24))

        self.login_button = primary_button(inner, text="Login", command=self.login)
        self.login_button.grid(row=6, column=0, sticky=tk.EW)

        self.login_status = ttk.Label(
            inner,
            text="",
            foreground=OrynTheme.color("danger"),
            background=OrynTheme.color("surface"),
            font=OrynTheme.font("small"),
        )
        self.login_status.grid(row=7, column=0, sticky=tk.W, pady=(14, 0))

    def create_register_widgets(self):
        self.register_frame.columnconfigure(0, weight=1)
        self.register_frame.rowconfigure(0, weight=1)

        form = self._build_split(
            self.register_frame,
            [
                "Create an account to store workspace snapshots in Oryn Cloud.",
                "Existing workspaces keep their snapshot history.",
            ],
        )

        card = card_frame(form, padding=(8, 0))
        card.grid(row=0, column=1, sticky=tk.EW, padx=(36, 48))
        card.columnconfigure(0, weight=1)

        inner = ttk.Frame(card, style="Oryn.Card.TFrame")
        inner.pack(fill=tk.BOTH, expand=True)
        inner.columnconfigure(0, weight=1)

        ttk.Label(inner, text="Register", style="Oryn.Card.Heading.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 4)
        )
        ttk.Label(
            inner,
            text="Set up your Oryn cloud workspace.",
            style="Oryn.Card.Metadata.TLabel",
        ).grid(row=1, column=0, sticky=tk.W, pady=(0, 26))

        ttk.Label(inner, text="EMAIL", style="Oryn.Card.Section.TLabel").grid(row=2, column=0, sticky=tk.W, pady=(0, 6))
        self.register_email = ttk.Entry(inner, width=36, style="Oryn.TEntry")
        self.register_email.grid(row=3, column=0, sticky=tk.EW, pady=(0, 16))

        ttk.Label(inner, text="PASSWORD", style="Oryn.Card.Section.TLabel").grid(row=4, column=0, sticky=tk.W, pady=(0, 6))
        self.register_password = ttk.Entry(inner, width=36, show="*", style="Oryn.TEntry")
        self.register_password.grid(row=5, column=0, sticky=tk.EW, pady=(0, 24))

        self.register_button = primary_button(inner, text="Register", command=self.register)
        self.register_button.grid(row=6, column=0, sticky=tk.EW)

        self.register_status = ttk.Label(
            inner,
            text="",
            foreground=OrynTheme.color("danger"),
            background=OrynTheme.color("surface"),
            font=OrynTheme.font("small"),
        )
        self.register_status.grid(row=7, column=0, sticky=tk.W, pady=(14, 0))

    def login(self):
        email = self.login_email.get().strip()
        password = self.login_password.get().strip()

        if not email or not password:
            self.login_status.config(text="Please enter email and password")
            return

        self.login_button.config(state=tk.DISABLED)
        self.login_status.config(text="Logging in...")

        thread = threading.Thread(target=self._login_thread, args=(email, password), daemon=True)
        thread.start()

    def _login_thread(self, email, password):
        try:
            temp_client = CloudClient()
            result = temp_client.login(email, password)
            token = result["access_token"]
            save_token(token)
            self.root.after(0, self.app.on_authenticated, token)
        except Exception as exc:
            self.root.after(0, self._login_failed, str(exc))

    def _login_failed(self, error_msg):
        self.login_status.config(text=f"Login failed: {error_msg}")
        self.login_button.config(state=tk.NORMAL)

    def register(self):
        email = self.register_email.get().strip()
        password = self.register_password.get().strip()

        if not email or not password:
            self.register_status.config(text="Please enter email and password")
            return

        self.register_button.config(state=tk.DISABLED)
        self.register_status.config(text="Registering...")

        thread = threading.Thread(target=self._register_thread, args=(email, password), daemon=True)
        thread.start()

    def _register_thread(self, email, password):
        try:
            temp_client = CloudClient()
            result = temp_client.register(email, password)
            token = result["access_token"]
            save_token(token)
            self.root.after(0, self.app.on_authenticated, token)
        except Exception as exc:
            self.root.after(0, self._register_failed, str(exc))

    def _register_failed(self, error_msg):
        self.register_status.config(text=f"Registration failed: {error_msg}")
        self.register_button.config(state=tk.NORMAL)


__all__ = ["AuthScreen"]
