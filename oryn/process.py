from oryn.applications.vscode.adapter import VSCodeAdapter


# CHANGED: Reuse the adapter's platform-aware VS Code behavior.
def get_vscode_process():
    return VSCodeAdapter().detect()


def get_active_file():
    return VSCodeAdapter().get_active_file()


def find_workspace_storage(active_file):
    return VSCodeAdapter().find_workspace_storage(active_file)
