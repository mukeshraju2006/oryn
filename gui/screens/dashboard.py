import threading
import tkinter as tk
from tkinter import ttk

try:
    from ..applications.vscode.adapter import VSCodeAdapter
    from ..applications.browsers.adapter import BrowserAdapter
    from ..cloud.session import load_token, save_token
    from ..components.buttons import (
        divider,
        ghost_button,
        primary_button,
        secondary_button,
        vertical_divider,
    )
    from ..components.cards import card_frame
    from ..components.status import ActivityLog
    from ..core.snapshot import Snapshot
    from ..theme import OrynTheme
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from oryn.applications.vscode.adapter import VSCodeAdapter
    from oryn.applications.browsers.adapter import BrowserAdapter
    from oryn.cloud.session import load_token, save_token
    from gui.components.buttons import (
        divider,
        ghost_button,
        primary_button,
        secondary_button,
        vertical_divider,
    )
    from gui.components.cards import card_frame
    from gui.components.status import ActivityLog
    from oryn.core.snapshot import Snapshot
    from gui.theme import OrynTheme


class DashboardScreen(tk.Frame):
    def __init__(self, parent, app):
        # CHANGED: light background for the composed dashboard.
        super().__init__(parent, bg=OrynTheme.color("bg"))
        self.app = app
        self.root = app.root
        self.client = app.client

        self.workspaces = []
        self.workspace_display_to_id = {}
        self.snapshots = []
        self.snapshot_display_to_id = {}

        self._capture_in_progress = False
        self._restore_in_progress = False
        self._loading_workspaces = False
        self._loading_snapshots = False

        self._build()

    def set_client(self, client):
        self.client = client

    def _build(self):
        # CHANGED: complete layout recomposition.
        # Row 0 is a slim top bar with a hairline divider at row 1; row 2 is
        # the body, a sidebar next to a larger scrollable content area.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._build_top_bar()
        self._build_body()

    # ------------------------------------------------------------------
    # Top bar
    # ------------------------------------------------------------------

    def _build_top_bar(self):
        bar = ttk.Frame(self, style="Oryn.TFrame")
        bar.grid(row=0, column=0, sticky=tk.EW)

        ttk.Label(
            bar,
            text="Oryn",
            style="Oryn.Heading.TLabel",
        ).pack(side=tk.LEFT, padx=(28, 0), pady=10)

        self.header_status = ttk.Label(
            bar,
            text="Ready",
            style="Oryn.Metadata.TLabel",
        )
        self.header_status.pack(side=tk.RIGHT, padx=(0, 28), pady=10)

        # CHANGED: divider is gridded in its own row (self is grid-managed).
        divider(self).grid(row=1, column=0, sticky=tk.EW)

    # ------------------------------------------------------------------
    # Body: sidebar + content
    # ------------------------------------------------------------------

    def _build_body(self):
        body = ttk.Frame(self, style="Oryn.TFrame")
        # CHANGED: body lives in row 2 (row 1 is the top-bar divider) and is
        # the stretch row, so the sidebar/content fill the window.
        body.grid(row=2, column=0, sticky=tk.NSEW)
        # CHANGED: minsize keeps the sidebar column wide; weights let the
        # content column absorb extra width.
        body.columnconfigure(0, weight=0, minsize=240)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sidebar(body)
        vertical_divider(body).grid(row=0, column=1, sticky=tk.NS)

        # CHANGED: dedicated host frame so the canvas + scrollbar can use
        # pack internally without mixing geometry managers on body.
        content_host = ttk.Frame(body, style="Oryn.TFrame")
        content_host.grid(row=0, column=2, sticky=tk.NSEW)
        self._build_content(content_host)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self, body):
        # CHANGED: no grid_propagate freeze - the sidebar sizes to its
        # content and stretches to the full body height via its grid cell.
        sidebar = ttk.Frame(body, style="Oryn.Sidebar.TFrame")
        sidebar.grid(row=0, column=0, sticky=tk.NSEW)
        sidebar.columnconfigure(0, weight=1)

        # Oryn identity block.
        ttk.Label(sidebar, text="Oryn", style="Oryn.Sidebar.Heading.TLabel").grid(
            row=0, column=0, sticky=tk.EW, padx=(24, 24), pady=(24, 2)
        )
        ttk.Label(
            sidebar,
            text="Workspace capture & restore",
            style="Oryn.Sidebar.Metadata.TLabel",
        ).grid(row=1, column=0, sticky=tk.EW, padx=(24, 24), pady=(0, 20))

        self._sidebar_section(sidebar, 2, "WORKSPACE")
        self.workspace_combo = ttk.Combobox(
            sidebar,
            state="readonly",
            style="Oryn.TCombobox",
        )
        self.workspace_combo.grid(row=3, column=0, sticky=tk.EW, padx=24, pady=(6, 18))
        self.workspace_combo.bind("<<ComboboxSelected>>", self.on_workspace_select)

        self._sidebar_section(sidebar, 4, "SNAPSHOT")
        self.snapshot_combo = ttk.Combobox(
            sidebar,
            state="readonly",
            style="Oryn.TCombobox",
        )
        self.snapshot_combo.grid(row=5, column=0, sticky=tk.EW, padx=24, pady=(6, 24))

        # Snapshot navigation: previous / next through the loaded list.
        nav = ttk.Frame(sidebar, style="Oryn.Sidebar.TFrame")
        nav.grid(row=6, column=0, sticky=tk.EW, padx=24)
        nav.columnconfigure(0, weight=1)
        nav.columnconfigure(1, weight=1)

        self.snapshot_prev_button = ghost_button(
            nav, text="\u2190  Previous", command=self.previous_snapshot
        )
        self.snapshot_prev_button.grid(row=0, column=0, sticky=tk.EW, padx=(0, 3))

        self.snapshot_next_button = ghost_button(
            nav, text="Next  \u2192", command=self.next_snapshot
        )
        self.snapshot_next_button.grid(row=0, column=1, sticky=tk.EW, padx=(3, 0))

        # CHANGED: session actions pinned to the bottom via a stretch spacer.
        spacer = ttk.Frame(sidebar, style="Oryn.Sidebar.TFrame")
        spacer.grid(row=7, column=0, sticky=tk.NSEW)
        sidebar.rowconfigure(7, weight=1)

        session = ttk.Frame(sidebar, style="Oryn.Sidebar.TFrame")
        session.grid(row=8, column=0, sticky=tk.EW, padx=24, pady=(0, 20))
        session.columnconfigure(0, weight=1)
        session.columnconfigure(1, weight=0)

        self.refresh_button = ghost_button(
            session, text="Refresh", command=self.refresh_workspaces
        )
        self.refresh_button.grid(row=0, column=0, sticky=tk.W)

        self.logout_button = ttk.Button(
            session,
            text="Logout",
            command=self.app.logout,
            style="Oryn.Terracotta.TButton",
        )
        self.logout_button.grid(row=0, column=1, sticky=tk.E)

    def _sidebar_section(self, sidebar, row, title):
        ttk.Label(sidebar, text=title, style="Oryn.Sidebar.Section.TLabel").grid(
            row=row, column=0, sticky=tk.EW, padx=24
        )

    # ------------------------------------------------------------------
    # Content area
    # ------------------------------------------------------------------

    def _build_content(self, host):
        # Canvas-based vertical scroll so the dashboard stays usable on
        # short windows.
        outer = tk.Canvas(
            host,
            bg=OrynTheme.color("bg"),
            highlightthickness=0,
            bd=0,
        )
        self.content_canvas = outer
        self.content_scrollbar = ttk.Scrollbar(
            host,
            orient="vertical",
            command=outer.yview,
            style="Oryn.Vertical.TScrollbar",
        )
        outer.configure(yscrollcommand=self._on_content_scroll)

        # CHANGED: scrollbar packed first so the canvas fills the remainder.
        self.content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.content = ttk.Frame(outer, style="Oryn.TFrame")
        self.content_window = outer.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._on_content_configure)
        outer.bind("<Configure>", self._on_canvas_configure)

        # Mouse-wheel scrolling while the pointer is over the content area.
        outer.bind_all("<MouseWheel>", self._on_mousewheel)

        self.content.columnconfigure(0, weight=1)
        self._build_content_body(self.content)

    def _build_content_body(self, content):
        content.columnconfigure(0, weight=1)

        # Workspace title block.
        title_row = ttk.Frame(content, style="Oryn.TFrame")
        title_row.grid(row=0, column=0, sticky=tk.EW, padx=(32, 32), pady=(28, 2))
        title_row.columnconfigure(0, weight=1)

        self.workspace_title = ttk.Label(
            title_row,
            text="No workspace selected",
            style="Oryn.Display.TLabel",
        )
        self.workspace_title.grid(row=0, column=0, sticky=tk.EW)

        self.workspace_meta = ttk.Label(
            title_row,
            text="Choose a workspace from the sidebar",
            style="Oryn.Metadata.TLabel",
        )
        self.workspace_meta.grid(row=1, column=0, sticky=tk.EW, pady=(3, 0))

        # CHANGED: divider gridded in its own row (content is grid-managed).
        divider(content).grid(row=1, column=0, sticky=tk.EW, padx=32, pady=(16, 0))

        # Snapshot summary block.
        summary = ttk.Frame(content, style="Oryn.TFrame")
        summary.grid(row=2, column=0, sticky=tk.EW, padx=32, pady=(20, 0))
        summary.columnconfigure(0, weight=1)

        ttk.Label(summary, text="CURRENT SNAPSHOT", style="Oryn.Section.TLabel").pack(anchor=tk.W)

        self.snapshot_summary = ttk.Label(
            summary,
            text="\u2014",
            style="Oryn.Heading.TLabel",
            wraplength=520,
            justify=tk.LEFT,
        )
        self.snapshot_summary.pack(anchor=tk.W, pady=(8, 0))

        self.snapshot_meta = ttk.Label(
            summary,
            text="",
            style="Oryn.Metadata.TLabel",
            wraplength=520,
            justify=tk.LEFT,
        )
        self.snapshot_meta.pack(anchor=tk.W, pady=(3, 0))

        # Application and state information.
        info = ttk.Frame(content, style="Oryn.TFrame")
        info.grid(row=3, column=0, sticky=tk.EW, padx=32, pady=(22, 0))
        info.columnconfigure(1, weight=1)

        ttk.Label(info, text="APPLICATION", style="Oryn.Section.TLabel").grid(row=0, column=0, sticky=tk.W, padx=(0, 16))
        self.app_value = ttk.Label(info, text="\u2014", style="Oryn.Secondary.TLabel")
        self.app_value.grid(row=0, column=1, sticky=tk.W)

        ttk.Label(info, text="LAST CAPTURED", style="Oryn.Section.TLabel").grid(row=1, column=0, sticky=tk.W, padx=(0, 16), pady=(10, 0))
        self.captured_value = ttk.Label(info, text="\u2014", style="Oryn.Secondary.TLabel")
        self.captured_value.grid(row=1, column=1, sticky=tk.W, pady=(10, 0))

        # Actions row: Capture is the strongest action, Restore quieter.
        actions = ttk.Frame(content, style="Oryn.TFrame")
        actions.grid(row=4, column=0, sticky=tk.EW, padx=32, pady=(26, 0))

        self.capture_button = primary_button(
            actions, text="Capture Workspace", command=self.capture_workspace
        )
        self.capture_button.pack(side=tk.LEFT)

        self.restore_button = secondary_button(
            actions, text="Restore Snapshot", command=self.restore_workspace
        )
        self.restore_button.pack(side=tk.LEFT, padx=(10, 0))

        # Activity history.
        ttk.Label(content, text="ACTIVITY", style="Oryn.Section.TLabel").grid(
            row=5, column=0, sticky=tk.EW, padx=32, pady=(30, 7)
        )

        self.status_text = ActivityLog(content, height=7)
        self.status_text.grid(row=6, column=0, sticky=tk.EW, padx=32, pady=(0, 28))

    # ------------------------------------------------------------------
    # Content scrolling helpers (presentation only)
    # ------------------------------------------------------------------

    def _on_content_scroll(self, first, last):
        self.content_scrollbar.set(first, last)
        # Only show the scrollbar when the content actually overflows.
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.content_scrollbar.pack_forget()
        elif not self.content_scrollbar.winfo_ismapped():
            self.content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_content_configure(self, event):
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.content_canvas.itemconfigure(self.content_window, width=event.width)

    def _on_mousewheel(self, event):
        # CHANGED: bounds check instead of winfo_containing.
        # winfo_containing raises KeyError for combobox popdown windows
        # (they exist in Tcl but not in the Python widget tree).
        if self.content_canvas.winfo_ismapped():
            x = self.content_canvas.winfo_rootx()
            y = self.content_canvas.winfo_rooty()
            w = self.content_canvas.winfo_width()
            h = self.content_canvas.winfo_height()
            if x <= event.x_root < x + w and y <= event.y_root < y + h:
                self.content_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    # ------------------------------------------------------------------
    # Snapshot navigation helpers (iterate the already-loaded snapshot list)
    # ------------------------------------------------------------------

    def previous_snapshot(self):
        values = list(self.snapshot_combo["values"])
        if not values:
            return
        try:
            index = values.index(self.snapshot_combo.get())
        except ValueError:
            index = 0
        new_index = max(0, index - 1)
        self.snapshot_combo.current(new_index)
        self._update_snapshot_summary(new_index)

    def next_snapshot(self):
        values = list(self.snapshot_combo["values"])
        if not values:
            return
        try:
            index = values.index(self.snapshot_combo.get())
        except ValueError:
            index = -1
        new_index = min(len(values) - 1, index + 1)
        self.snapshot_combo.current(new_index)
        self._update_snapshot_summary(new_index)

    def _update_snapshot_summary(self, index):
        """Present the snapshot at index from the already-loaded list."""
        if index < 0 or index >= len(self.snapshots):
            return
        snap = self.snapshots[index]
        snapshot_id = snap.get("id")
        version = snap.get("version")
        created = snap.get("created_at")

        display_name = f"Snapshot {snapshot_id} (v{version})"
        self.snapshot_summary.config(text=display_name)

        meta_bits = []
        if version is not None:
            meta_bits.append(f"Version {version}")
        if created:
            meta_bits.append(f"Captured {self._format_timestamp(created)}")
        self.snapshot_meta.config(text="  \u00b7  ".join(meta_bits))

        if snapshot_id is not None:
            self.snapshot_display_to_id[display_name] = snapshot_id

        # CHANGED: the newest snapshot doubles as the "last captured" metadata.
        if index == 0:
            self.captured_value.config(
                text=self._format_timestamp(created) if created else "\u2014"
            )
            self.app_value.config(text="VS Code \u00b7 Browser URLs")

    @staticmethod
    def _format_timestamp(value):
        """Trim the server timestamp string for display (presentation only)."""
        text = str(value)
        return text[:16].replace("T", " ")

    def _update_header_status(self, text):
        self.header_status.config(text=text)

    def _update_workspace_header(self):
        """Reflect the selected workspace in the content header."""
        selection = self.workspace_combo.get()
        if selection:
            workspace_id = self.workspace_display_to_id.get(selection, "?")
            self.workspace_title.config(text=selection)
            self.workspace_meta.config(text=f"Workspace #{workspace_id}")
        else:
            self.workspace_title.config(text="No workspace selected")
            self.workspace_meta.config(text="Choose a workspace from the sidebar")

    # CHANGED: activity log entry point also feeds the quiet header status.
    def log_status(self, message):
        self.status_text.append(message)
        self._update_header_status(message)
        self.root.update_idletasks()

    def set_buttons_state(self, capture_state=None, restore_state=None, refresh_state=None, workspace_state=None, snapshot_state=None):
        if capture_state is not None:
            self.capture_button.config(state=capture_state)
        if restore_state is not None:
            self.restore_button.config(state=restore_state)
        if refresh_state is not None:
            self.refresh_button.config(state=refresh_state)
        if workspace_state is not None:
            self.workspace_combo.config(state=workspace_state)
        if snapshot_state is not None:
            self.snapshot_combo.config(state=snapshot_state)

    def load_user_data(self):
        self.log_status("Loading workspaces...")
        self._loading_workspaces = True
        self.set_buttons_state(refresh_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)

        thread = threading.Thread(target=self._load_user_data_thread, daemon=True)
        thread.start()

    def _load_user_data_thread(self):
        try:
            if not self.client:
                self.root.after(0, self.log_status, "Error: Not logged in")
                return
            workspaces = self.client.list_workspaces()
            self.workspaces = workspaces
            self.root.after(0, self._update_workspace_combo)
        except Exception as exc:
            self.root.after(0, self.log_status, f"Failed to load workspaces: {exc}")
        finally:
            self.root.after(0, self._finish_loading_workspaces)

    def _finish_loading_workspaces(self):
        self._loading_workspaces = False
        self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly")
        self._update_workspace_combo()

    def _update_workspace_combo(self):
        self.workspace_display_to_id.clear()
        workspace_names = []

        for ws in self.workspaces:
            display_name = ws["name"]
            workspace_names.append(display_name)
            self.workspace_display_to_id[display_name] = ws["id"]

        self.workspace_combo["values"] = workspace_names
        if workspace_names:
            self.workspace_combo.current(0)
            self.on_workspace_select(None)
        self._update_workspace_header()
        self.log_status(f"Loaded {len(self.workspaces)} workspaces")

    def on_workspace_select(self, event):
        if self._loading_snapshots:
            return

        selection = self.workspace_combo.get()
        if not selection:
            return

        # CHANGED: reflect the selection in the content header.
        self._update_workspace_header()
        self.snapshot_summary.config(text="Loading\u2026")
        self.snapshot_meta.config(text="")

        workspace_id = self.workspace_display_to_id.get(selection)
        if not workspace_id:
            return

        self.log_status(f"Loading snapshots for workspace: {selection}")
        self._loading_snapshots = True
        self.set_buttons_state(refresh_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)

        thread = threading.Thread(target=self._load_snapshots_thread, args=(workspace_id,), daemon=True)
        thread.start()

    def _load_snapshots_thread(self, workspace_id):
        try:
            if not self.client:
                self.root.after(0, self.log_status, "Error: Not logged in")
                return

            snapshots = self.client.list_snapshots(workspace_id=workspace_id)
            self.snapshots = snapshots
            self.root.after(0, self._update_snapshot_combo)
        except Exception as exc:
            self.root.after(0, self.log_status, f"Failed to load snapshots: {exc}")
        finally:
            self.root.after(0, self._finish_loading_snapshots)

    def _finish_loading_snapshots(self):
        self._loading_snapshots = False
        self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly", snapshot_state="readonly")

    def _update_snapshot_combo(self):
        self.snapshot_display_to_id.clear()
        snapshot_names = []

        for snap in self.snapshots:
            snapshot_id = snap.get("id")
            version = snap.get("version")
            if snapshot_id is None:
                continue
            display_name = f"Snapshot {snapshot_id} (v{version})"
            snapshot_names.append(display_name)
            self.snapshot_display_to_id[display_name] = snapshot_id

        self.snapshot_combo.set("")
        self.snapshot_combo.configure(values=())

        if snapshot_names:
            self.snapshot_combo.configure(values=tuple(snapshot_names))
            self.snapshot_combo.current(0)

        # CHANGED: present the newest snapshot in the content summary.
        if self.snapshots:
            self._update_snapshot_summary(0)
        else:
            self.snapshot_summary.config(text="No snapshots yet")
            self.snapshot_meta.config(text="Capture this workspace to create the first snapshot")

        self.log_status(f"Loaded {len(self.snapshots)} snapshots")

    def capture_workspace(self):
        if self._capture_in_progress:
            return

        self.log_status("Starting workspace capture...")
        self._capture_in_progress = True
        self.set_buttons_state(capture_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)

        thread = threading.Thread(target=self._capture_workspace_thread, daemon=True)
        thread.start()

    def _capture_workspace_thread(self):
        try:
            if not self.client:
                self.root.after(0, self.log_status, "Error: Not logged in")
                return

            vscode_adapter = VSCodeAdapter()
            snapshot = vscode_adapter.capture()

            browser_adapter = BrowserAdapter()
            browser_urls = browser_adapter.capture_urls()

            if snapshot is not None:
                snapshot.browser_urls = browser_urls
            elif browser_urls:
                snapshot = Snapshot(application="browser", workspace={}, files=[], layout={}, active_file=None, browser_urls=browser_urls)

            if snapshot is None:
                self.root.after(0, self.log_status, "Capture failed: No supported application is open")
                return

            self.root.after(0, self.log_status, f"Captured {len(browser_urls)} browser URL(s)")

            workspace_selection = self.workspace_combo.get()
            if not workspace_selection:
                workspace_name = f"Oryn Workspace {len(self.workspaces) + 1}"
                result = self.client.create_workspace(workspace_name)
                workspace_id = result["id"]
                new_workspace = {"id": workspace_id, "name": workspace_name}
                self.workspaces.append(new_workspace)
                self.workspace_display_to_id[workspace_name] = workspace_id
                self.root.after(0, self._update_workspace_combo)
            else:
                workspace_id = self.workspace_display_to_id.get(workspace_selection)
                if not workspace_id:
                    self.root.after(0, self.log_status, "Error: Could not find selected workspace")
                    return

            self.root.after(0, self.log_status, "Uploading snapshot...")
            result = self.client.create_snapshot(workspace_id=workspace_id, snapshot=snapshot)
            self.root.after(0, self.log_status, f"Capture successful! Snapshot ID: {result['id']}, Version: {result['version']}")
            self.root.after(0, self._reload_current_workspace_snapshots)
        except Exception as exc:
            self.root.after(0, self.log_status, f"Capture failed: {exc}")
        finally:
            self.root.after(0, self._finish_capture)

    def _reload_current_workspace_snapshots(self):
        if self._loading_snapshots:
            return
        selection = self.workspace_combo.get()
        if not selection:
            return
        self.on_workspace_select(None)

    def _finish_capture(self):
        self._capture_in_progress = False
        self.set_buttons_state(capture_state=tk.NORMAL, workspace_state="readonly", snapshot_state="readonly")

    def restore_workspace(self):
        if self._restore_in_progress:
            return

        selection = self.snapshot_combo.get()
        if not selection:
            self.log_status("Please select a snapshot to restore")
            return

        snapshot_id = self.snapshot_display_to_id.get(selection)
        if not snapshot_id:
            self.log_status("Invalid snapshot selection")
            return

        self.log_status(f"Starting restore of snapshot {snapshot_id}...")
        self._restore_in_progress = True
        self.set_buttons_state(restore_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)

        thread = threading.Thread(target=self._restore_workspace_thread, args=(snapshot_id,), daemon=True)
        thread.start()

    def _restore_workspace_thread(self, snapshot_id):
        try:
            if not self.client:
                self.root.after(0, self.log_status, "Error: Not logged in")
                return

            workspace_selection = self.workspace_combo.get()
            if not workspace_selection:
                self.root.after(0, self.log_status, "Error: No workspace selected")
                return

            workspace_id = self.workspace_display_to_id.get(workspace_selection)
            if not workspace_id:
                self.root.after(0, self.log_status, "Error: Could not find selected workspace")
                return

            snapshot = self.client.get_snapshot(workspace_id, snapshot_id)
            if not snapshot:
                self.root.after(0, self.log_status, "Error: Snapshot not found")
                return

            if isinstance(snapshot, dict):
                application = snapshot.get("application")
                browser_urls = snapshot.get("browser_urls", [])
            else:
                application = getattr(snapshot, "application", None)
                browser_urls = getattr(snapshot, "browser_urls", [])

            success = True
            if application == "vscode":
                vscode_adapter = VSCodeAdapter()
                success = vscode_adapter.restore(snapshot)

            if success:
                browser_adapter = BrowserAdapter()
                restored_browser_count = browser_adapter.restore_urls(browser_urls)
                self.root.after(0, self.log_status, f"Opened {restored_browser_count} browser URL(s)")
                self.root.after(0, self.log_status, f"Restore successful! Workspace restored from snapshot {snapshot_id}")
            else:
                self.root.after(0, self.log_status, "Restore failed: VS Code restoration failed")
        except Exception as exc:
            self.root.after(0, self.log_status, f"Restore failed: {exc}")
        finally:
            self.root.after(0, self._finish_restore)

    def _finish_restore(self):
        self._restore_in_progress = False
        self.set_buttons_state(restore_state=tk.NORMAL, workspace_state="readonly", snapshot_state="readonly")

    def refresh_workspaces(self):
        if self._loading_workspaces or self._loading_snapshots:
            return

        self.log_status("Refreshing workspaces and snapshots...")
        self._loading_workspaces = True
        self.set_buttons_state(refresh_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)

        thread = threading.Thread(target=self._refresh_workspaces_thread, daemon=True)
        thread.start()

    def _refresh_workspaces_thread(self):
        try:
            if not self.client:
                self.root.after(0, self.log_status, "Error: Not logged in")
                return

            workspaces = self.client.list_workspaces()
            self.root.after(0, self._finish_refresh_workspaces, workspaces)
        except Exception as exc:
            self.root.after(0, self._refresh_failed, str(exc))

    def _finish_refresh_workspaces(self, workspaces):
        self.workspaces = workspaces
        self._loading_workspaces = False
        self._update_workspace_combo()
        self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly")

    def _refresh_failed(self, error_message):
        self._loading_workspaces = False
        self._loading_snapshots = False
        self.log_status(f"Refresh failed: {error_message}")
        self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly", snapshot_state="readonly")

    def clear_state(self):
        self.client = None
        self.workspaces = []
        self.workspace_display_to_id.clear()
        self.snapshots = []
        self.snapshot_display_to_id.clear()
        self.workspace_combo.set("")
        self.workspace_combo.configure(values=())
        self.snapshot_combo.set("")
        self.snapshot_combo.configure(values=())

        # CHANGED: reset the composed content presentation as well.
        self._update_workspace_header()
        self.snapshot_summary.config(text="\u2014")
        self.snapshot_meta.config(text="")
        self.app_value.config(text="\u2014")
        self.captured_value.config(text="\u2014")


__all__ = ["DashboardScreen"]
