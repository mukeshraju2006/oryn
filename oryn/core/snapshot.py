class Snapshot:

    def __init__(
        self,
        application,
        workspace,
        files,
        layout,
        active_file,
        editor_state=None,
        text_editor_state=None,
        project=None,
        browser_urls=None,          # CHANGED
    ):
        # CHANGED:
        # Version 5 adds browser URL capture.
        self.version = 5

        self.application = application

        self.workspace = workspace

        self.files = files

        self.layout = layout

        self.active_file = active_file

        self.editor_state = editor_state

        self.text_editor_state = text_editor_state

        self.project = project

        # CHANGED:
        # URLs of browser tabs that were open when
        # this snapshot was captured.
        self.browser_urls = browser_urls or []

    def to_dict(self):
        return {
            "version": self.version,

            "application": self.application,

            "workspace": self.workspace,

            "files": self.files,

            "layout": self.layout,

            "active_file": self.active_file,

            "editor_state": self.editor_state,

            "text_editor_state": self.text_editor_state,

            "project": self.project,

            # CHANGED:
            # Store browser URLs as part of the snapshot.
            "browser_urls": self.browser_urls,
        }