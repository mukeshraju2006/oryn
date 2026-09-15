import sys
import os
import threading
import tkinter as tk
from tkinter import ttk

# Try relative imports first (when run as part of the oryn package)
try:
    from ..cloud.client import CloudClient
    from ..cloud.session import load_token, save_token
    from ..applications.vscode.adapter import VSCodeAdapter
except ImportError:
    # Fallback for when the module is run directly (e.g., python gui/app.py)
    # Add the project root to the path so we can import oryn
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from oryn.cloud.client import CloudClient
    from oryn.cloud.session import load_token, save_token
    from oryn.applications.vscode.adapter import VSCodeAdapter


class OrynGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Oryn - VS Code Workspace Sync")
        self.root.geometry("500x400")
        self.root.minsize(400, 300)

        self.client = None
        self.token = None
        # Store workspace objects with their display names
        self.workspaces = []  # List of dicts: {"id": "...", "name": "..."}
        self.workspace_display_to_id = {}  # Maps display name to workspace id
        # Store snapshot objects with their display names
        self.snapshots = []  # List of dicts: {"id": "...", "version": "...", ...}
        self.snapshot_display_to_id = {}  # Maps display name to snapshot id

        # Track ongoing operations to manage button states
        self._capture_in_progress = False
        self._restore_in_progress = False
        self._loading_workspaces = False
        self._loading_snapshots = False

        # Create a notebook (tabbed interface) for login/register and main dashboard
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Login frame
        self.login_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.login_frame, text="Login")
        self.create_login_widgets()

        # Register frame
        self.register_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.register_frame, text="Register")
        self.create_register_widgets()

        # Main dashboard frame (initially hidden)
        self.dashboard_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.dashboard_frame, text="Dashboard")
        self.create_dashboard_widgets()

        # If we have a token, try to load user data
        self.token = load_token()
        if self.token:
            self.client = CloudClient(token=self.token)
            self.notebook.select(2)  # Switch to dashboard
            # Validate token by trying to load user data
            self.log_status("Validating session...")
            self.load_user_data()
        else:
            self.notebook.select(0)  # Login tab

    def create_login_widgets(self):
        # Email
        ttk.Label(self.login_frame, text="Email:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.login_email = ttk.Entry(self.login_frame, width=30)
        self.login_email.grid(row=0, column=1, padx=5, pady=5)

        # Password
        ttk.Label(self.login_frame, text="Password:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.login_password = ttk.Entry(self.login_frame, width=30, show="*")
        self.login_password.grid(row=1, column=1, padx=5, pady=5)

        # Login button
        self.login_button = ttk.Button(
            self.login_frame, text="Login", command=self.login
        )
        self.login_button.grid(row=2, column=0, columnspan=2, pady=10)

        # Status label
        self.login_status = ttk.Label(self.login_frame, text="", foreground="red")
        self.login_status.grid(row=3, column=0, columnspan=2)

    def create_register_widgets(self):
        # Email
        ttk.Label(self.register_frame, text="Email:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.register_email = ttk.Entry(self.register_frame, width=30)
        self.register_email.grid(row=0, column=1, padx=5, pady=5)

        # Password
        ttk.Label(self.register_frame, text="Password:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.register_password = ttk.Entry(self.register_frame, width=30, show="*")
        self.register_password.grid(row=1, column=1, padx=5, pady=5)

        # Register button
        self.register_button = ttk.Button(
            self.register_frame, text="Register", command=self.register
        )
        self.register_button.grid(row=2, column=0, columnspan=2, pady=10)

        # Status label
        self.register_status = ttk.Label(self.register_frame, text="", foreground="red")
        self.register_status.grid(row=3, column=0, columnspan=2)

    def create_dashboard_widgets(self):
        # Welcome label
        self.welcome_label = ttk.Label(self.dashboard_frame, text="Welcome to Oryn")
        self.welcome_label.grid(row=0, column=0, columnspan=2, padx=5, pady=(10, 5))

        # Workspace selection
        ttk.Label(self.dashboard_frame, text="Workspace:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.workspace_combo = ttk.Combobox(self.dashboard_frame, state="readonly", width=30)
        self.workspace_combo.grid(row=1, column=1, padx=5, pady=5)
        self.workspace_combo.bind("<<ComboboxSelected>>", self.on_workspace_select)

        # Snapshot selection
        ttk.Label(self.dashboard_frame, text="Snapshot:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        self.snapshot_combo = ttk.Combobox(self.dashboard_frame, state="readonly", width=30)
        self.snapshot_combo.grid(row=2, column=1, padx=5, pady=5)

        # Buttons frame
        buttons_frame = ttk.Frame(self.dashboard_frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=10)

        # Capture button
        self.capture_button = ttk.Button(
            buttons_frame, text="Capture Workspace", command=self.capture_workspace
        )
        self.capture_button.grid(row=0, column=0, padx=5)

        # Restore button
        self.restore_button = ttk.Button(
            buttons_frame, text="Restore Workspace", command=self.restore_workspace
        )
        self.restore_button.grid(row=0, column=1, padx=5)

        # Refresh button
        self.refresh_button = ttk.Button(
            buttons_frame, text="Refresh", command=self.refresh_workspaces
        )
        self.refresh_button.grid(row=0, column=2, padx=5)

        # Logout button
        self.logout_button = ttk.Button(
            buttons_frame, text="Logout", command=self.logout
        )
        self.logout_button.grid(row=0, column=3, padx=5)

        # Status area
        ttk.Label(self.dashboard_frame, text="Status:").grid(row=4, column=0, padx=5, pady=(10, 5), sticky=tk.W)
        self.status_text = tk.Text(self.dashboard_frame, height=8, width=50)
        self.status_text.grid(row=5, column=0, columnspan=2, padx=5, pady=5)
        self.status_text.config(state=tk.DISABLED)

        # Make the text widget expand with the window
        self.dashboard_frame.rowconfigure(5, weight=1)
        self.dashboard_frame.columnconfigure(0, weight=1)

    def log_status(self, message):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def set_buttons_state(self, capture_state=None, restore_state=None, refresh_state=None,
                         workspace_state=None, snapshot_state=None):
        """Helper to set button and combobox states without affecting others unless specified."""
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
        # Logout button is always enabled unless we are in a critical operation (we'll keep it simple)
        # Login and register buttons are managed by the notebook tab selection

    def login(self):
        email = self.login_email.get().strip()
        password = self.login_password.get().strip()

        if not email or not password:
            self.login_status.config(text="Please enter email and password")
            return

        self.login_button.config(state=tk.DISABLED)
        self.login_status.config(text="Logging in...")

        # Run in thread to avoid blocking GUI
        thread = threading.Thread(target=self._login_thread, args=(email, password))
        thread.daemon = True
        thread.start()

    def _login_thread(self, email, password):
        try:
            # Create a new client for login (without token)
            temp_client = CloudClient()
            result = temp_client.login(email, password)
            self.token = result["access_token"]
            save_token(self.token)
            self.client = CloudClient(token=self.token)

            # Update GUI in main thread
            self.root.after(0, self._login_success)
        except Exception as e:
            self.root.after(0, self._login_failed, str(e))

    def _login_success(self):
        self.login_status.config(text="Login successful!")
        self.notebook.select(2)  # Switch to dashboard
        self.load_user_data()
        self.login_button.config(state=tk.NORMAL)

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

        # Run in thread to avoid blocking GUI
        thread = threading.Thread(target=self._register_thread, args=(email, password))
        thread.daemon = True
        thread.start()

    def _register_thread(self, email, password):
        try:
            temp_client = CloudClient()
            result = temp_client.register(email, password)
            self.token = result["access_token"]
            save_token(self.token)
            self.client = CloudClient(token=self.token)

            # Update GUI in main thread
            self.root.after(0, self._register_success)
        except Exception as e:
            self.root.after(0, self._register_failed, str(e))

    def _register_success(self):
        # Registration successful and we're already logged in
        self.register_status.config(text="Registration successful! You are now logged in.")
        self.notebook.select(2)  # Switch to dashboard
        self.load_user_data()
        self.register_button.config(state=tk.NORMAL)

    def _register_failed(self, error_msg):
        self.register_status.config(text=f"Registration failed: {error_msg}")
        self.register_button.config(state=tk.NORMAL)

    def load_user_data(self):
        self.log_status("Loading workspaces...")
        # Run in thread to avoid blocking GUI
        self._loading_workspaces = True
        self.set_buttons_state(refresh_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)
        thread = threading.Thread(target=self._load_user_data_thread)
        thread.daemon = True
        thread.start()

    def _load_user_data_thread(self):
        try:
            if not self.client:
                self.root.after(0, lambda: self.log_status("Error: Not logged in"))
                return

            workspaces = self.client.list_workspaces()
            self.workspaces = workspaces

            # Update GUI in main thread
            self.root.after(0, self._update_workspace_combo)
        except Exception as e:
            self.root.after(0, lambda: self.log_status(f"Failed to load workspaces: {e}"))
        finally:
            # Reset loading state in main thread
            self.root.after(0, self._finish_loading_workspaces)

    def _finish_loading_workspaces(self):
        self._loading_workspaces = False
        self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly")
        self._update_workspace_combo()

    def _update_workspace_combo(self):
        # Clear previous mappings
        self.workspace_display_to_id.clear()
        workspace_names = []
        for ws in self.workspaces:
            display_name = ws["name"]
            workspace_names.append(display_name)
            self.workspace_display_to_id[display_name] = ws["id"]

        self.workspace_combo["values"] = workspace_names
        if workspace_names:
            self.workspace_combo.current(0)
            self.on_workspace_select(None)  # Load snapshots for first workspace
        self.log_status(f"Loaded {len(self.workspaces)} workspaces")

    def on_workspace_select(self, event):
        if self._loading_snapshots:
            # Ignore selection changes while loading snapshots
            return
        selection = self.workspace_combo.get()
        if not selection:
            return

        # Get the workspace ID from our mapping
        workspace_id = self.workspace_display_to_id.get(selection)
        if not workspace_id:
            return

        self.log_status(f"Loading snapshots for workspace: {selection}")
        # Run in thread to avoid blocking GUI
        self._loading_snapshots = True
        self.set_buttons_state(refresh_state=tk.DISABLED, workspace_state=tk.DISABLED)
        thread = threading.Thread(target=self._load_snapshots_thread, args=(workspace_id,))
        thread.daemon = True
        thread.start()

    def _load_snapshots_thread(self, workspace_id):
        try:
            if not self.client:
                self.root.after(0, lambda: self.log_status("Error: Not logged in"))
                return

            snapshots = self.client.list_snapshots(workspace_id=workspace_id)
            self.snapshots = snapshots

            # Update GUI in main thread
            self.root.after(0, self._update_snapshot_combo)
        except Exception as e:
            self.root.after(0, lambda: self.log_status(f"Failed to load snapshots: {e}"))
        finally:
            # Reset loading state in main thread
            self.root.after(0, self._finish_loading_snapshots)

    def _finish_loading_snapshots(self):
        self._loading_snapshots = False
        self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly")
        self._update_snapshot_combo()

    def _update_snapshot_combo(self):
        # Clear previous mappings
        self.snapshot_display_to_id.clear()
        snapshot_names = []
        for snap in self.snapshots:
            display_name = f"Snapshot {snap['id']} (v{snap['version']})"
            snapshot_names.append(display_name)
            self.snapshot_display_to_id[display_name] = snap["id"]

        self.snapshot_combo["values"] = snapshot_names
        if snapshot_names:
            self.snapshot_combo.current(0)
        self.log_status(f"Loaded {len(self.snapshots)} snapshots")

    def capture_workspace(self):
        if self._capture_in_progress:
            return
        self.log_status("Starting workspace capture...")
        self._capture_in_progress = True
        self.set_buttons_state(capture_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)
        # Run in thread to avoid blocking GUI
        thread = threading.Thread(target=self._capture_workspace_thread)
        thread.daemon = True
        thread.start()

    def _capture_workspace_thread(self):
        try:
            if not self.client:
                self.root.after(0, lambda: self.log_status("Error: Not logged in"))
                return

            adapter = VSCodeAdapter()
            snapshot = adapter.capture()

            if not snapshot:
                self.root.after(0, lambda: self.log_status("Capture failed: No snapshot generated"))
                return

            # Get the currently selected workspace for upload
            workspace_selection = self.workspace_combo.get()
            if not workspace_selection:
                # If no workspace selected, create a new one
                workspace_name = f"Oryn Workspace {len(self.workspaces) + 1}"
                result = self.client.create_workspace(workspace_name)
                workspace_id = result["id"]
                # Add to our workspace list
                new_workspace = {"id": workspace_id, "name": workspace_name}
                self.workspaces.append(new_workspace)
                self.workspace_display_to_id[workspace_name] = workspace_id
                # Update the combobox
                self.root.after(0, lambda: self.workspace_combo["values"].append(workspace_name))
                self.root.after(0, lambda: self.workspace_combo.set(workspace_name))
                self.root.after(0, self._update_workspace_combo)  # Refresh mappings
            else:
                # Use the currently selected workspace
                workspace_id = self.workspace_display_to_id.get(workspace_selection)
                if not workspace_id:
                    self.root.after(0, lambda: self.log_status("Error: Could not find selected workspace"))
                    return

            # Upload snapshot
            self.root.after(0, lambda: self.log_status("Uploading snapshot..."))
            result = self.client.create_snapshot(workspace_id=workspace_id, snapshot=snapshot)

            self.root.after(0, lambda: self.log_status(
                f"Capture successful! Snapshot ID: {result['id']}, Version: {result['version']}"
            ))
            # Reload snapshots for the current workspace
            if self.workspace_combo.get():
                self.on_workspace_select(None)

        except Exception as e:
            self.root.after(0, lambda: self.log_status(f"Capture failed: {e}"))
        finally:
            # Reset capture state in main thread
            self.root.after(0, self._finish_capture)

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

        # Get the snapshot ID from our mapping
        snapshot_id = self.snapshot_display_to_id.get(selection)
        if not snapshot_id:
            self.log_status("Invalid snapshot selection")
            return

        self.log_status(f"Starting restore of snapshot {snapshot_id}...")
        self._restore_in_progress = True
        self.set_buttons_state(restore_state=tk.DISABLED, workspace_state=tk.DISABLED, snapshot_state=tk.DISABLED)
        # Run in thread to avoid blocking GUI
        thread = threading.Thread(target=self._restore_workspace_thread, args=(snapshot_id,))
        thread.daemon = True
        thread.start()

    def _restore_workspace_thread(self, snapshot_id):
        try:
            if not self.client:
                self.root.after(0, lambda: self.log_status("Error: Not logged in"))
                return

            # Get the selected workspace
            workspace_selection = self.workspace_combo.get()
            if not workspace_selection:
                self.root.after(0, lambda: self.log_status("Error: No workspace selected"))
                return

            workspace_id = self.workspace_display_to_id.get(workspace_selection)
            if not workspace_id:
                self.root.after(0, lambda: self.log_status("Error: Could not find selected workspace"))
                return

            # Get the snapshot
            snapshot = self.client.get_snapshot(workspace_id, snapshot_id)
            if not snapshot:
                self.root.after(0, lambda: self.log_status("Error: Snapshot not found"))
                return

            # Use the VSCode adapter to restore
            adapter = VSCodeAdapter()
            success = adapter.restore(snapshot)

            if success:
                self.root.after(0, lambda: self.log_status(
                    f"Restore successful! Workspace restored from snapshot {snapshot_id}"
                ))
            else:
                self.root.after(0, lambda: self.log_status("Restore failed: Adapter returned false"))

        except Exception as e:
            self.root.after(0, lambda: self.log_status(f"Restore failed: {e}"))
        finally:
            # Reset restore state in main thread
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
        # Run in thread to avoid blocking GUI
        thread = threading.Thread(target=self._refresh_workspaces_thread)
        thread.daemon = True
        thread.start()

    def _refresh_workspaces_thread(self):
        try:
            if not self.client:
                self.root.after(0, lambda: self.log_status("Error: Not logged in"))
                return

            # Reload workspaces
            workspaces = self.client.list_workspaces()
            self.workspaces = workspaces

            # Update GUI in main thread
            self.root.after(0, self._update_workspace_combo)
            # After updating workspaces, we need to reload snapshots for the current workspace
            # But note: _update_workspace_combo will call on_workspace_select(None) if there is a selection
            # which will trigger loading snapshots. However, we want to avoid double loading.
            # We'll let the normal flow handle it: after setting workspaces, the combo box will trigger
            # on_workspace_select if the selection changed, but we want to keep the current selection and
            # just refresh its snapshots.
            # We'll do a quick hack: after setting workspaces, we manually trigger a snapshot reload for the
            # current workspace without changing the workspace selection.
            if self.workspace_combo.get():
                current_selection = self.workspace_combo.get()
                workspace_id = self.workspace_display_to_id.get(current_selection)
                if workspace_id:
                    # Load snapshots for the current workspace
                    self._loading_snapshots = True
                    self.set_buttons_state(refresh_state=tk.DISABLED, workspace_state=tk.DISABLED)
                    snapshots = self.client.list_snapshots(workspace_id=workspace_id)
                    self.snapshots = snapshots
                    self.root.after(0, self._update_snapshot_combo)
                    self.root.after(0, lambda: setattr(self, '_loading_snapshots', False))
                    self.root.after(0, lambda: self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly"))
        except Exception as e:
            self.root.after(0, lambda: self.log_status(f"Refresh failed: {e}"))
        finally:
            # Reset loading state in main thread
            self.root.after(0, lambda: setattr(self, '_loading_workspaces', False))
            self.root.after(0, lambda: self.set_buttons_state(refresh_state=tk.NORMAL, workspace_state="readonly"))

    def logout(self):
        # Clear the token
        self.token = None
        # Remove the saved token file
        from oryn.cloud.session import TOKEN_FILE
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        # Clear the client
        self.client = None
        # Clear workspace and snapshot data
        self.workspaces = []
        self.workspace_display_to_id.clear()
        self.snapshots = []
        self.snapshot_display_to_id.clear()
        # Switch to login screen
        self.notebook.select(0)
        self.log_status("Logged out successfully.")


def main():
    root = tk.Tk()
    app = OrynGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()