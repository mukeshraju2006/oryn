import json
import subprocess
import urllib.parse
from pathlib import Path

from oryn.core.snapshot import Snapshot


class VSCodeAdapter:

    def detect(self):
        result = subprocess.run(
            ["pgrep", "-f", "/usr/share/code/code$"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def get_active_file(self):
        result = subprocess.run(
            ["code", "--status"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():
            line = line.strip()

            if "Window (" in line:
                window = line.split("Window (", 1)[1]

                if " - " in window:
                    return window.split(" - ")[0]

        return None

    def find_workspace_storage(self, active_file):
        workspace_storage = (
            Path.home()
            / ".config"
            / "Code"
            / "User"
            / "workspaceStorage"
        )

        if not workspace_storage.exists():
            return None

        for directory in workspace_storage.iterdir():

            state_db = directory / "state.vscdb"
            workspace_file = directory / "workspace.json"

            if not state_db.exists() or not workspace_file.exists():
                continue

            result = subprocess.run(
                [
                    "sqlite3",
                    str(state_db),
                    "SELECT value FROM ItemTable "
                    "WHERE key='memento/workbench.parts.editor';",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                continue

            if active_file not in result.stdout:
                continue

            try:
                workspace_data = json.loads(
                    workspace_file.read_text()
                )

                return {
                    "workspace_id": directory.name,
                    "workspace_path": workspace_data.get("folder"),
                    "state_db": str(state_db),
                }

            except (json.JSONDecodeError, OSError):
                continue

        return None

    def get_editor_state(self, state_db):
        result = subprocess.run(
            [
                "sqlite3",
                state_db,
                "SELECT value FROM ItemTable "
                "WHERE key='memento/workbench.parts.editor';",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def parse_editor_state(self, editor_state):
        try:
            data = json.loads(editor_state)

            editor_part = data["editorpart.state"]
            grid = editor_part["serializedGrid"]

            root = grid["root"]

            editors = []

            def walk(node):

                if node["type"] == "leaf":

                    for editor in node["data"].get("editors", []):

                        if (
                            editor["id"]
                            != "workbench.editors.files.fileEditorInput"
                        ):
                            continue

                        editor_data = json.loads(
                            editor["value"]
                        )

                        resource = editor_data["resourceJSON"]

                        editors.append(
                            {
                                "path": resource["fsPath"],
                                "uri": resource["external"],
                            }
                        )

                elif node["type"] == "branch":

                    for child in node["data"]:
                        walk(child)

            walk(root)

            return {
                "editors": editors,
                "active_group": editor_part.get(
                    "activeGroup"
                ),
                "most_recent_active_groups": editor_part.get(
                    "mostRecentActiveGroups",
                    [],
                ),
            }

        except (
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ):
            return None

    def get_text_editor_state(self, state_db):
        result = subprocess.run(
            [
                "sqlite3",
                state_db,
                "SELECT value FROM ItemTable "
                "WHERE key='memento/workbench.editors.files.textFileEditor';",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        try:
            return json.loads(
                result.stdout.strip()
            )

        except json.JSONDecodeError:
            return None

    def parse_text_editor_state(
        self,
        text_editor_state,
        open_editors,
    ):
        try:
            view_states = text_editor_state[
                "textEditorViewState"
            ]

            # Only keep files that are currently open.
            open_paths = {
                editor["path"]
                for editor in open_editors
            }

            result = {}

            for entry in view_states:

                file_uri, file_data = entry

                parsed_uri = urllib.parse.urlparse(
                    file_uri
                )

                file_path = parsed_uri.path

                # Ignore historical/closed files.
                if file_path not in open_paths:
                    continue

                for group_id, editor_state in file_data.items():

                    cursor_states = editor_state.get(
                        "cursorState",
                        []
                    )

                    view_state = editor_state.get(
                        "viewState",
                        {}
                    )

                    if not cursor_states:
                        continue

                    cursor = cursor_states[0]

                    position = cursor.get(
                        "position",
                        {}
                    )

                    selection_start = cursor.get(
                        "selectionStart",
                        {}
                    )

                    first_position = view_state.get(
                        "firstPosition",
                        {}
                    )

                    result[file_path] = {
                        "group": int(group_id),

                        "cursor": {
                            "line": position.get(
                                "lineNumber"
                            ),
                            "column": position.get(
                                "column"
                            ),
                        },

                        "selection_start": {
                            "line": selection_start.get(
                                "lineNumber"
                            ),
                            "column": selection_start.get(
                                "column"
                            ),
                        },

                        "scroll": {
                            "line": first_position.get(
                                "lineNumber"
                            ),
                            "column": first_position.get(
                                "column"
                            ),
                        },

                        "scroll_left": view_state.get(
                            "scrollLeft",
                            0,
                        ),

                        "first_position_delta_top": view_state.get(
                            "firstPositionDeltaTop",
                            0,
                        ),
                    }

            return result

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return None
    
        # CHANGED: Find the VS Code Hot Exit backup for a specific file.
    def find_unsaved_backup(self, file_path):

        backups_root = (
            Path.home()
            / ".config"
            / "Code"
            / "Backups"
        )

        if not backups_root.exists():
            return None

        file_uri = Path(file_path).as_uri()

        # Walk through all VS Code backup files.
        for backup_directory in backups_root.iterdir():

            if not backup_directory.is_dir():
                continue

            file_directory = backup_directory / "file"

            if not file_directory.exists():
                continue

            for backup_file in file_directory.iterdir():

                if not backup_file.is_file():
                    continue

                try:
                    with backup_file.open(
                        "r",
                        encoding="utf-8",
                        errors="replace",
                    ) as file:

                        first_line = file.readline().strip()

                        if not first_line:
                            continue

                        # VS Code stores:
                        #
                        # file-uri {"metadata": "..."}
                        #
                        parts = first_line.split(" ", 1)

                        if len(parts) != 2:
                            continue

                        backup_uri = parts[0]

                        if backup_uri != file_uri:
                            continue

                        # Everything after the first line is the
                        # actual unsaved file content.
                        content = file.read()

                        return {
                            "path": file_path,
                            "content": content,
                            "backup": str(backup_file),
                        }

                except OSError:
                    continue

        return None

    def capture(self):
        pid = self.detect()

        if not pid:
            return None

        active_file = self.get_active_file()

        if not active_file:
            return None

        workspace = self.find_workspace_storage(
            active_file
        )

        if not workspace:
            return None

        editor_state = self.get_editor_state(
            workspace["state_db"]
        )

        if not editor_state:
            return None

        parsed_editor_state = self.parse_editor_state(
            editor_state
        )

        if not parsed_editor_state:
            return None

        text_editor_state = self.get_text_editor_state(
            workspace["state_db"]
        )

        parsed_text_editor_state = {}

        if text_editor_state:
            parsed_text_editor_state = (
                self.parse_text_editor_state(
                    text_editor_state,
                    parsed_editor_state["editors"],
                )
                or {}
            )

        editors = []

        for editor in parsed_editor_state["editors"]:

            path = editor["path"]

            editor_data = {
                "path": path,
                "uri": editor["uri"],
            }

            if path in parsed_text_editor_state:
                editor_data.update(
                    parsed_text_editor_state[path]
                )

            editors.append(editor_data)

        # CHANGED: Capture unsaved changes for currently open files.
        unsaved_changes = {}

        for editor in editors:

            backup = self.find_unsaved_backup(
                editor["path"]
            )

            if backup:
                unsaved_changes[
                    editor["path"]
                ] = backup["content"]

        return Snapshot(
            application="vscode",
            workspace={
                "id": workspace["workspace_id"],
                "path": workspace["workspace_path"],
            },
            active_file=active_file,
            editors=editors,
            unsaved_changes=unsaved_changes,  # CHANGED
        )