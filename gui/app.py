import os
import sys
import tkinter as tk

try:
    from .cloud.client import CloudClient
    from .cloud.session import SESSION_FILE, load_token
    from .screens.auth import AuthScreen
    from .screens.dashboard import DashboardScreen
    from .theme import apply_theme
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from oryn.cloud.client import CloudClient
    from oryn.cloud.session import SESSION_FILE, load_token
    from gui.screens.auth import AuthScreen
    from gui.screens.dashboard import DashboardScreen
    from gui.theme import apply_theme


class OrynApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Oryn")
        # CHANGED: larger default window for the sidebar + content layout.
        self.root.geometry("980x640")
        self.root.minsize(820, 560)
        # CHANGED: warm light window chrome.
        self.root.configure(bg="#F5F3EE")
        apply_theme(self.root)

        self.client = None
        self.token = None

        # CHANGED: warm light container.
        self.container = tk.Frame(self.root, bg="#F5F3EE")
        self.container.pack(fill=tk.BOTH, expand=True)

        self.auth_screen = AuthScreen(self.container, self)
        self.dashboard_screen = DashboardScreen(self.container, self)

        self.show_screen("auth")

        self.token = load_token()
        if self.token:
            self.on_authenticated(self.token)

    def show_screen(self, screen_name):
        for screen in (self.auth_screen, self.dashboard_screen):
            screen.pack_forget()

        if screen_name == "dashboard":
            self.dashboard_screen.pack(fill=tk.BOTH, expand=True)
        else:
            self.auth_screen.pack(fill=tk.BOTH, expand=True)

    def on_authenticated(self, token):
        self.token = token
        self.client = CloudClient(token=token)
        self.dashboard_screen.set_client(self.client)
        self.show_screen("dashboard")
        self.dashboard_screen.log_status("Validating session...")
        self.dashboard_screen.load_user_data()

    def logout(self):
        self.token = None
        self.client = None

        if SESSION_FILE.exists():
            SESSION_FILE.unlink()

        self.dashboard_screen.clear_state()
        self.auth_screen.notebook.select(0)
        if hasattr(self.auth_screen, "login_status"):
            self.auth_screen.login_status.config(text="")
        if hasattr(self.auth_screen, "register_status"):
            self.auth_screen.register_status.config(text="")
        self.show_screen("auth")
        self.dashboard_screen.log_status("Logged out successfully.")


class OrynGUI(OrynApp):
    pass


def main():
    root = tk.Tk()
    app = OrynApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
