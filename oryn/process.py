import subprocess
from pathlib import Path
import json


def get_vscode_process():
    result = subprocess.run(
        ["pgrep", "-f", "/usr/share/code/code$"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def get_active_file():
    # CHANGED: Get the active VS Code window/file from `code --status`
    result = subprocess.run(
        ["code", "--status"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        line = line.strip()

        if "Window (" in line:
            # Example:
            # | Window (cli.py - oryn - Visual Studio Code)
            window = line.split("Window (", 1)[1]

            if " - " in window:
                return window.split(" - ")[0]

    return None


def find_workspace_storage(active_file):
    workspace_storage = (
        Path.home()
        / ".config"
        / "Code"
        / "User"
        / "workspaceStorage"
    )

    # CHANGED: Search each workspace database for the active file
    for directory in workspace_storage.iterdir():
        db = directory / "state.vscdb"

        if not db.exists():
            continue

        result = subprocess.run(
            [
                "sqlite3",
                str(db),
                "SELECT value FROM ItemTable "
                "WHERE key='memento/workbench.parts.editor';"
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            continue

        if active_file in result.stdout:
            workspace_file = directory / "workspace.json"

            if workspace_file.exists():
                try:
                    data = json.loads(workspace_file.read_text())

                    return {
                        "workspace_id": directory.name,
                        "workspace_path": data.get("folder"),
                        "state_db": str(db),
                    }

                except (json.JSONDecodeError, OSError):
                    continue

    return None