class Snapshot:

    def __init__(
        self,
        application,
        workspace,
        active_file,
        editors,
        unsaved_changes=None,  # CHANGED: added unsaved changes
    ):
        self.version = 1
        self.application = application
        self.workspace = workspace
        self.active_file = active_file
        self.editors = editors
        self.unsaved_changes = unsaved_changes or {}  # CHANGED

    def to_dict(self):
        return {
            "version": self.version,
            "application": self.application,
            "workspace": self.workspace,
            "active_file": self.active_file,
            "editors": self.editors,
            "unsaved_changes": self.unsaved_changes,  # CHANGED
        }