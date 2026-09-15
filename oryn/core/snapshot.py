class Snapshot:

    def __init__(
        self,
        application,
        workspace,
        files,
        layout,
        active_file,
        editor_state=None,          # CHANGED
        text_editor_state=None,     # CHANGED
        project=None,               # CHANGED
    ):
        # CHANGED:
        # Snapshot version increased because we now preserve
        # the VS Code raw state and portable project data.
        self.version = 4

        self.application = application

        self.workspace = workspace

        self.files = files

        self.layout = layout

        self.active_file = active_file

        # CHANGED:
        # Preserve VS Code's original editor layout state.
        self.editor_state = editor_state

        # CHANGED:
        # Preserve VS Code's original text editor state,
        # including cursor, selection and scroll information.
        self.text_editor_state = text_editor_state

        # CHANGED:
        # Preserve the portable project tree so a missing
        # destination project can be recreated from the snapshot.
        self.project = project

    def to_dict(self):
        return {
            "version": self.version,

            "application": self.application,

            "workspace": self.workspace,

            "files": self.files,

            "layout": self.layout,

            "active_file": self.active_file,

            # CHANGED:
            # Store raw VS Code editor layout state.
            "editor_state": self.editor_state,

            # CHANGED:
            # Store raw VS Code text editor state.
            "text_editor_state": self.text_editor_state,

            # CHANGED:
            # Store the portable project tree.
            "project": self.project,
        }
