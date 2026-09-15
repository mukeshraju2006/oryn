import base64
import json
import sqlite3
import subprocess
import time
import urllib.parse
from pathlib import Path

from oryn.core.snapshot import Snapshot


class VSCodeAdapter:

    def detect(self):

        result = subprocess.run(
            [
                "pgrep",
                "-f",
                "/usr/share/code/code$",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def get_active_file(self):

        result = subprocess.run(
            [
                "code",
                "--status",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        for line in result.stdout.splitlines():

            line = line.strip()

            if "Window (" not in line:
                continue

            window = line.split(
                "Window (",
                1,
            )[1]

            if " - " not in window:
                continue

            active_file = window.split(
                " - ",
                1,
            )[0]

            active_file = (
                active_file
                .lstrip("●")
                .strip()
            )

            if not active_file:
                return None

            return active_file

        return None

    def get_workspace_storages(self):

        workspace_storage = (
            Path.home()
            / ".config"
            / "Code"
            / "User"
            / "workspaceStorage"
        )

        if not workspace_storage.exists():
            return []

        workspaces = []

        for directory in workspace_storage.iterdir():

            if not directory.is_dir():
                continue

            state_db = (
                directory / "state.vscdb"
            )

            workspace_file = (
                directory / "workspace.json"
            )

            if (
                not state_db.exists()
                or not workspace_file.exists()
            ):
                continue

            try:

                workspace_data = json.loads(
                    workspace_file.read_text()
                )

                workspace_path = (
                    workspace_data.get(
                        "folder"
                    )
                )

                if not workspace_path:
                    continue

                workspaces.append(
                    {
                        "workspace_id": directory.name,
                        "workspace_path": workspace_path,
                        "state_db": str(state_db),
                    }
                )

            except (
                json.JSONDecodeError,
                OSError,
            ):
                continue

        return workspaces

    def find_workspace_storage(
        self,
        active_file=None,
        workspace_path=None,
    ):

        workspaces = (
            self.get_workspace_storages()
        )

        if not workspaces:
            return None

        # CHANGED:
        # Normalize file:// workspace URIs before comparing paths.
        if workspace_path:

            target_path = (
                self.normalize_workspace_path(
                    workspace_path
                )
            )

            target_path = str(
                Path(target_path).resolve()
            )

            for workspace in workspaces:

                stored_path = (
                    self.normalize_workspace_path(
                        workspace["workspace_path"]
                    )
                )

                stored_path = str(
                    Path(stored_path).resolve()
                )

                if stored_path == target_path:
                    return workspace

        if active_file:

            for workspace in workspaces:

                result = subprocess.run(
                    [
                        "sqlite3",
                        workspace["state_db"],
                        "SELECT value FROM ItemTable "
                        "WHERE key='memento/"
                        "workbench.parts.editor';",
                    ],
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    continue

                if active_file in result.stdout:
                    return workspace

        status = subprocess.run(
            [
                "code",
                "--status",
            ],
            capture_output=True,
            text=True,
        )

        if status.returncode == 0:

            status_output = (
                status.stdout
            )

            for workspace in workspaces:

                stored_path = (
                    self.normalize_workspace_path(
                        workspace["workspace_path"]
                    )
                )

                if stored_path in status_output:
                    return workspace

        if len(workspaces) == 1:
            return workspaces[0]

        return None

    def get_editor_state(
        self,
        state_db,
    ):

        result = subprocess.run(
            [
                "sqlite3",
                state_db,
                "SELECT value FROM ItemTable "
                "WHERE key='memento/"
                "workbench.parts.editor';",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    def parse_editor_state(
        self,
        editor_state,
    ):

        try:

            data = json.loads(
                editor_state
            )

            editor_part = data[
                "editorpart.state"
            ]

            grid = editor_part[
                "serializedGrid"
            ]

            root = grid["root"]

            editors = []

            groups = []

            group_counter = 0

            def walk(node):

                nonlocal group_counter

                if node["type"] == "leaf":

                    group_id = group_counter

                    group_counter += 1

                    group_files = []

                    for editor in node[
                        "data"
                    ].get(
                        "editors",
                        [],
                    ):

                        if (
                            editor["id"]
                            !=
                            "workbench.editors.files.fileEditorInput"
                        ):
                            continue

                        try:

                            editor_data = json.loads(
                                editor["value"]
                            )

                            resource = (
                                editor_data[
                                    "resourceJSON"
                                ]
                            )

                            file_data = {
                                "path": resource[
                                    "fsPath"
                                ],
                                "uri": resource[
                                    "external"
                                ],
                                "group": group_id,
                            }

                            editors.append(
                                file_data
                            )

                            group_files.append(
                                resource[
                                    "fsPath"
                                ]
                            )

                        except (
                            KeyError,
                            TypeError,
                            json.JSONDecodeError,
                        ):
                            continue

                    groups.append(
                        {
                            "id": group_id,
                            "editors": group_files,
                        }
                    )

                elif node["type"] == "branch":

                    for child in node["data"]:
                        walk(child)

            walk(root)

            layout = {
                "groups": groups,

                "active_group": (
                    editor_part.get(
                        "activeGroup"
                    )
                ),

                "most_recent_active_groups": (
                    editor_part.get(
                        "mostRecentActiveGroups",
                        [],
                    )
                ),
            }

            return {
                "editors": editors,
                "layout": layout,
            }

        except (
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ):
            return None

    def get_text_editor_state(
        self,
        state_db,
    ):

        result = subprocess.run(
            [
                "sqlite3",
                state_db,
                "SELECT value FROM ItemTable "
                "WHERE key='memento/"
                "workbench.editors.files."
                "textFileEditor';",
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

            view_states = (
                text_editor_state[
                    "textEditorViewState"
                ]
            )

            open_paths = {
                editor["path"]
                for editor in open_editors
            }

            result = {}

            for entry in view_states:

                file_uri, file_data = entry

                parsed_uri = (
                    urllib.parse.urlparse(
                        file_uri
                    )
                )

                file_path = (
                    urllib.parse.unquote(
                        parsed_uri.path
                    )
                )

                if file_path not in open_paths:
                    continue

                for (
                    group_id,
                    editor_state,
                ) in file_data.items():

                    cursor_states = (
                        editor_state.get(
                            "cursorState",
                            [],
                        )
                    )

                    view_state = (
                        editor_state.get(
                            "viewState",
                            {},
                        )
                    )

                    if not cursor_states:
                        continue

                    cursor = cursor_states[0]

                    position = cursor.get(
                        "position",
                        {},
                    )

                    selection_start = (
                        cursor.get(
                            "selectionStart",
                            {},
                        )
                    )

                    selection_end = (
                        cursor.get(
                            "position",
                            {},
                        )
                    )

                    first_position = (
                        view_state.get(
                            "firstPosition",
                            {},
                        )
                    )

                    result[file_path] = {

                        "group": int(
                            group_id
                        ),

                        "cursor": {

                            "line": position.get(
                                "lineNumber"
                            ),

                            "column": position.get(
                                "column"
                            ),
                        },

                        "selection": {

                            "start": {

                                "line": (
                                    selection_start.get(
                                        "lineNumber"
                                    )
                                ),

                                "column": (
                                    selection_start.get(
                                        "column"
                                    )
                                ),
                            },

                            "end": {

                                "line": (
                                    selection_end.get(
                                        "lineNumber"
                                    )
                                ),

                                "column": (
                                    selection_end.get(
                                        "column"
                                    )
                                ),
                            },
                        },

                        "scroll": {

                            "line": (
                                first_position.get(
                                    "lineNumber"
                                )
                            ),

                            "column": (
                                first_position.get(
                                    "column"
                                )
                            ),
                        },

                        "scroll_left": (
                            view_state.get(
                                "scrollLeft",
                                0,
                            )
                        ),

                        "first_position_delta_top": (
                            view_state.get(
                                "firstPositionDeltaTop",
                                0,
                            )
                        ),
                    }

            return result

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

    def find_unsaved_backup(
        self,
        file_path,
    ):

        backups_root = (
            Path.home()
            / ".config"
            / "Code"
            / "Backups"
        )

        if not backups_root.exists():
            return None

        file_uri = Path(
            file_path
        ).as_uri()

        for backup_directory in (
            backups_root.iterdir()
        ):

            if not backup_directory.is_dir():
                continue

            file_directory = (
                backup_directory / "file"
            )

            if not file_directory.exists():
                continue

            for backup_file in (
                file_directory.iterdir()
            ):

                if not backup_file.is_file():
                    continue

                try:

                    with backup_file.open(
                        "r",
                        encoding="utf-8",
                        errors="replace",
                    ) as file:

                        first_line = (
                            file.readline().strip()
                        )

                        if not first_line:
                            continue

                        parts = first_line.split(
                            " ",
                            1,
                        )

                        if len(parts) != 2:
                            continue

                        backup_uri = parts[0]

                        if (
                            backup_uri
                            != file_uri
                        ):
                            continue

                        content = file.read()

                        return {
                            "path": file_path,
                            "content": content,
                        }

                except OSError:
                    continue

        return None

    def capture_unsaved_changes(
        self,
        editors,
    ):

        unsaved_changes = {}

        for editor in editors:

            path = editor["path"]

            backup = (
                self.find_unsaved_backup(
                    path
                )
            )

            if backup:

                unsaved_changes[
                    path
                ] = backup["content"]

        return unsaved_changes

    # CHANGED:
    # Capture the complete portable project tree relative to
    # the workspace root. Dependency, cache, and build directories
    # are intentionally excluded because they are machine-generated
    # and can be recreated on the destination machine.
    def capture_project(
        self,
        workspace_path,
        files,
    ):

        workspace = Path(
            workspace_path
        ).resolve()

        excluded_directories = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            "dist",
            "build",
            ".next",
            ".cache",
        }

        # CHANGED:
        # Use unsaved editor contents instead of the on-disk version.
        unsaved_content = {}

        for file_data in files:

            if not file_data.get(
                "unsaved"
            ):
                continue

            path = file_data.get(
                "path"
            )

            content = file_data.get(
                "content"
            )

            if not path or content is None:
                continue

            try:

                relative = (
                    Path(path)
                    .resolve()
                    .relative_to(workspace)
                )

                unsaved_content[
                    str(relative)
                ] = content.encode(
                    "utf-8"
                )

            except (
                ValueError,
                OSError,
            ):
                continue

        project_files = []

        directories = []

        if (
            not workspace.exists()
            or not workspace.is_dir()
        ):

            return {
                "root": ".",
                "directories": [],
                "files": [],
            }

        # CHANGED:
        # os.walk lets us prune dependency/cache directories before
        # entering them, instead of recursively scanning their contents.
        import os

        for (
            current_root,
            directory_names,
            file_names,
        ) in os.walk(workspace):

            current_path = Path(
                current_root
            )

            directory_names[:] = sorted(
                name
                for name in directory_names
                if (
                    name
                    not in excluded_directories
                    and not (
                        current_path / name
                    ).is_symlink()
                )
            )

            for directory_name in (
                directory_names
            ):

                directory_path = (
                    current_path
                    / directory_name
                )

                try:

                    relative = (
                        directory_path
                        .relative_to(
                            workspace
                        )
                    )

                    directories.append(
                        str(relative)
                    )

                except ValueError:
                    continue

            for file_name in sorted(
                file_names
            ):

                file_path = (
                    current_path
                    / file_name
                )

                if (
                    file_path.is_symlink()
                    or not file_path.is_file()
                ):
                    continue

                try:

                    relative = (
                        file_path.relative_to(
                            workspace
                        )
                    )

                    relative_string = str(
                        relative
                    )

                    if (
                        relative_string
                        in unsaved_content
                    ):

                        raw_data = (
                            unsaved_content[
                                relative_string
                            ]
                        )

                    else:

                        raw_data = (
                            file_path.read_bytes()
                        )

                    project_files.append(
                        {
                            "path": relative_string,
                            "data": base64.b64encode(
                                raw_data
                            ).decode(
                                "ascii"
                            ),
                            "size": len(
                                raw_data
                            ),
                            "encoding": "base64",
                        }
                    )

                except OSError as error:

                    print(
                        f"Could not capture project file "
                        f"{file_path}: {error}"
                    )

        return {
            "root": ".",
            "directories": sorted(
                directories
            ),
            "files": sorted(
                project_files,
                key=lambda item: item[
                    "path"
                ],
            ),
        }

    # CHANGED:
    # Map a Linux source workspace under /home/<user> to the
    # equivalent path under the current user's home directory.
    #
    # IMPORTANT:
    # The source may be a VS Code file:// URI, so normalize it
    # before converting it to a Path.
    def map_workspace_to_current_home(
        self,
        source_workspace,
    ):

        # CHANGED:
        # Normalize file:// URI before Path operations.
        source_workspace = (
            self.normalize_workspace_path(
                source_workspace
            )
        )

        source = Path(
            source_workspace
        ).resolve()

        parts = source.parts

        if (
            len(parts) < 3
            or parts[0] != "/"
            or parts[1] != "home"
        ):

            return None

        source_home = (
            Path("/")
            / "home"
            / parts[2]
        )

        try:

            relative = (
                source.relative_to(
                    source_home
                )
            )

        except ValueError:

            return None

        return (
            Path.home()
            / relative
        )

    # CHANGED:
    # Recreate a missing project from the cloud snapshot.
    def restore_project(
        self,
        project,
        destination_workspace,
    ):

        destination = (
            Path(
                destination_workspace
            ).resolve()
        )

        # CHANGED:
        # Validate that destination is a valid directory path
        if not destination.is_absolute():
            print(
                f"Destination workspace path must be absolute: "
                f"{destination_workspace}"
            )
            return False

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        # CHANGED:
        # Double-check that destination directory was created successfully
        if not destination.is_dir():
            print(
                f"Failed to create destination workspace directory: "
                f"{destination_workspace}"
            )
            return False

        directories = project.get(
            "directories",
            [],
        )

        for relative_path in directories:

            target = (
                destination
                / relative_path
            )

            try:
                target.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                # CHANGED:
                # Validate that created directory is within destination
                if not self._is_path_within_directory(target, destination):
                    print(
                        f"Skipping unsafe project directory (path traversal): "
                        f"{relative_path}"
                    )
                    # Remove the incorrectly created directory
                    try:
                        target.rmdir()
                    except OSError:
                        pass  # Ignore errors during cleanup
                    continue

            except OSError as error:

                print(
                    f"Could not create project "
                    f"directory {target}: {error}"
                )

                return False

        for file_data in project.get(
            "files",
            [],
        ):

            relative_path = (
                file_data.get(
                    "path"
                )
            )

            encoded_data = (
                file_data.get(
                    "data"
                )
            )

            if (
                not relative_path
                or encoded_data is None
            ):
                continue

            relative = Path(
                relative_path
            )

            if (
                relative.is_absolute()
                or ".." in relative.parts
            ):

                print(
                    f"Skipping unsafe project path: "
                    f"{relative_path}"
                )

                continue

            target = (
                destination
                / relative
            )

            try:

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                # CHANGED:
                # Validate that target file is within destination
                if not self._is_path_within_directory(target, destination):
                    print(
                        f"Skipping unsafe project file (path traversal): "
                        f"{relative_path}"
                    )
                    continue

                raw_data = (
                    base64.b64decode(
                        encoded_data
                    )
                )

                target.write_bytes(
                    raw_data
                )

            except (
                OSError,
                ValueError,
            ) as error:

                print(
                    f"Could not restore project "
                    f"file {target}: {error}"
                )

                return False

        return True

    # CHANGED:
    # Helper method to check if a path is within a directory
    def _is_path_within_directory(self, path, directory):
        """
        Check if a path is within a directory, resolving symlinks and
        preventing path traversal attacks.

        Args:
            path: Path to check
            directory: Directory that should contain the path

        Returns:
            bool: True if path is within directory, False otherwise
        """
        try:
            # Resolve both paths to eliminate symlinks and normalize
            resolved_path = path.resolve()
            resolved_directory = directory.resolve()

            # Check if the resolved path starts with the resolved directory
            return resolved_path.is_relative_to(resolved_directory)
        except (ValueError, OSError):
            # If resolution fails, consider it unsafe
            return False

    # CHANGED:
    # Recursively replace paths inside VS Code's
    # serialized JSON structures.
    def replace_paths(
        self,
        value,
        source_root,
        destination_root,
    ):

        if isinstance(
            value,
            str,
        ):

            if value.startswith(
                source_root
            ):

                return (
                    destination_root
                    + value[
                        len(source_root):
                    ]
                )

            source_uri = Path(
                source_root
            ).as_uri()

            destination_uri = Path(
                destination_root
            ).as_uri()

            if value.startswith(
                source_uri
            ):

                return (
                    destination_uri
                    + value[
                        len(source_uri):
                    ]
                )

            return value

        if isinstance(
            value,
            list,
        ):

            return [
                self.replace_paths(
                    item,
                    source_root,
                    destination_root,
                )
                for item in value
            ]

        if isinstance(
            value,
            dict,
        ):

            return {
                key: self.replace_paths(
                    item,
                    source_root,
                    destination_root,
                )
                for key, item in value.items()
            }

        return value

    # CHANGED:
    # Convert snapshot paths to destination paths.
    def remap_snapshot_paths(
        self,
        snapshot_data,
        destination_root,
    ):

        workspace = snapshot_data.get(
            "workspace",
            {},
        )

        source_workspace = (
            workspace.get("path")
        )

        if not source_workspace:
            return snapshot_data

        source_workspace = (
            self.normalize_workspace_path(
                source_workspace
            )
        )

        source_workspace = str(
            Path(
                source_workspace
            ).resolve()
        )

        destination_root = str(
            Path(
                destination_root
            ).resolve()
        )

        # CHANGED:
        # Remap complete raw VS Code state.
        if snapshot_data.get(
            "editor_state"
        ):

            snapshot_data[
                "editor_state"
            ] = self.replace_paths(
                snapshot_data[
                    "editor_state"
                ],
                source_workspace,
                destination_root,
            )

        if snapshot_data.get(
            "text_editor_state"
        ):

            snapshot_data[
                "text_editor_state"
            ] = self.replace_paths(
                snapshot_data[
                    "text_editor_state"
                ],
                source_workspace,
                destination_root,
            )

        # CHANGED:
        # Remap readable file records.
        for file_data in snapshot_data.get(
            "files",
            [],
        ):

            path = file_data.get(
                "path"
            )

            if path:

                path = str(
                    Path(path)
                )

                if path.startswith(
                    source_workspace
                ):

                    file_data["path"] = (
                        destination_root
                        + path[
                            len(source_workspace):
                        ]
                    )

            uri = file_data.get(
                "uri"
            )

            if uri:

                source_uri = Path(
                    source_workspace
                ).as_uri()

                destination_uri = Path(
                    destination_root
                ).as_uri()

                if uri.startswith(
                    source_uri
                ):

                    file_data["uri"] = (
                        destination_uri
                        + uri[
                            len(source_uri):
                        ]
                    )

        active_file = snapshot_data.get(
            "active_file"
        )

        if active_file:

            if active_file.startswith(
                source_workspace
            ):

                snapshot_data[
                    "active_file"
                ] = (
                    destination_root
                    + active_file[
                        len(source_workspace):
                    ]
                )

        # CHANGED:
        # Update workspace path itself.
        snapshot_data[
            "workspace"
        ]["path"] = destination_root

        return snapshot_data

    # CHANGED:
    # Find a workspace storage by its filesystem path.
    def find_storage_by_path(
        self,
        workspace_path,
    ):

        workspace_path = str(
            Path(
                workspace_path
            ).resolve()
        )

        for workspace in (
            self.get_workspace_storages()
        ):

            stored_path = (
                workspace[
                    "workspace_path"
                ]
            )

            stored_path = (
                self.normalize_workspace_path(
                    stored_path
                )
            )

            stored_path = str(
                Path(
                    stored_path
                ).resolve()
            )

            if (
                stored_path
                == workspace_path
            ):

                return workspace

        return None

    # CHANGED:
    # Write a VS Code ItemTable value using Python's
    # sqlite3 module instead of relying on shell commands.
    def write_state_value(
        self,
        state_db,
        key,
        value,
    ):

        connection = None

        try:

            connection = sqlite3.connect(
                state_db
            )

            connection.execute(
                """
                INSERT INTO ItemTable
                    (key, value)
                VALUES
                    (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET
                    value = excluded.value
                """,
                (
                    key,
                    json.dumps(value),
                ),
            )

            connection.commit()

            return True

        except sqlite3.Error as error:

            print(
                f"Could not update VS Code state "
                f"{key}: {error}"
            )

            return False

        finally:

            if connection:
                connection.close()

    # CHANGED:
    # Restore raw VS Code state into destination
    # workspace storage.
    def restore_raw_state(
        self,
        state_db,
        snapshot_data,
    ):

        editor_state = snapshot_data.get(
            "editor_state"
        )

        text_editor_state = (
            snapshot_data.get(
                "text_editor_state"
            )
        )

        success = True

        if editor_state:

            if not self.write_state_value(
                state_db,
                (
                    "memento/"
                    "workbench.parts.editor"
                ),
                editor_state,
            ):

                success = False

        if text_editor_state:

            if not self.write_state_value(
                state_db,
                (
                    "memento/"
                    "workbench.editors.files."
                    "textFileEditor"
                ),
                text_editor_state,
            ):

                success = False

        return success

    def normalize_workspace_path(
        self,
        workspace_path,
    ):

        if workspace_path.startswith(
            "file://"
        ):

            return urllib.parse.unquote(
                urllib.parse.urlparse(
                    workspace_path
                ).path
            )

        return workspace_path

    def restore_unsaved_files(
        self,
        files,
    ):

        for file_data in files:

            if not file_data.get(
                "unsaved",
                False,
            ):
                continue

            path = file_data.get(
                "path"
            )

            content = file_data.get(
                "content"
            )

            if (
                not path
                or content is None
            ):
                continue

            file_path = Path(
                path
            )

            try:

                if file_path.exists():

                    backup_path = Path(
                        str(file_path)
                        + ".oryn-backup"
                    )

                    backup_path.write_bytes(
                        file_path.read_bytes()
                    )

                file_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                file_path.write_text(
                    content,
                    encoding="utf-8",
                )

            except OSError as error:

                print(
                    f"Could not restore "
                    f"unsaved file {path}: "
                    f"{error}"
                )

    # CHANGED:
    # Launch the destination workspace first so VS Code
    # creates its workspaceStorage directory.
    def prepare_destination_workspace(
        self,
        workspace_path,
    ):

        subprocess.Popen(
            [
                "code",
                workspace_path,
            ]
        )

        # Give VS Code time to initialize workspace storage.
        time.sleep(3)

        return self.find_storage_by_path(
            workspace_path
        )

    # CHANGED:
    # Close VS Code before directly modifying state.vscdb.
    #
    # This prevents VS Code from overwriting our restored
    # database state while it is running.
    def close_vscode(self):

        result = subprocess.run(
            [
                "pkill",
                "-f",
                "/usr/share/code/code$",
            ],
            capture_output=True,
            text=True,
        )

        # pkill returning 1 simply means there was
        # nothing left to kill.
        if result.returncode not in (
            0,
            1,
        ):

            print(
                "Could not close VS Code."
            )

            return False

        # CHANGED:
        # Give VS Code processes time to terminate
        # and flush their database.
        time.sleep(2)

        return True

    # CHANGED:
    # Open VS Code after raw state has been restored.
    def launch_restored_workspace(
        self,
        workspace_path,
    ):

        subprocess.Popen(
            [
                "code",
                workspace_path,
            ]
        )

    def capture(self):

        # CHANGED:
        # Do not require process detection here.
        # VS Code's --status output and workspaceStorage database
        # are sufficient to identify the active workspace.
        active_file = (
            self.get_active_file()
        )

        workspace = (
            self.find_workspace_storage(
                active_file
            )
        )

        if not workspace:
            return None

        editor_state_raw = (
            self.get_editor_state(
                workspace["state_db"]
            )
        )

        editors = []

        layout = {
            "groups": [],
            "active_group": None,
            "most_recent_active_groups": [],
        }

        if editor_state_raw:

            parsed_editor_state = (
                self.parse_editor_state(
                    editor_state_raw
                )
            )

            if parsed_editor_state:

                editors = (
                    parsed_editor_state[
                        "editors"
                    ]
                )

                layout = (
                    parsed_editor_state[
                        "layout"
                    ]
                )

        text_editor_state_raw = (
            self.get_text_editor_state(
                workspace["state_db"]
            )
        )

        parsed_text_editor_state = {}

        if text_editor_state_raw:

            parsed_text_editor_state = (
                self.parse_text_editor_state(
                    text_editor_state_raw,
                    editors,
                )
                or {}
            )

        files = []

        for editor in editors:

            path = editor["path"]

            file_data = {

                "path": path,

                "uri": editor["uri"],

                "group": editor["group"],

                "active": (
                    path == active_file
                ),
            }

            if (
                path
                in parsed_text_editor_state
            ):

                file_data.update(
                    parsed_text_editor_state[
                        path
                    ]
                )

                file_data["group"] = (
                    editor["group"]
                )

            files.append(
                file_data
            )

        # CHANGED:
        # VS Code --status can report only a basename such as
        # "adapter.py", while the editor state contains the
        # complete filesystem path.
        #
        # Resolve the basename against the captured editors.
        if active_file:

            matching_active_files = [
                file_data["path"]
                for file_data in files
                if Path(
                    file_data["path"]
                ).name == active_file
            ]

            if len(
                matching_active_files
            ) == 1:

                active_file = (
                    matching_active_files[0]
                )

            elif active_file in {
                file_data["path"]
                for file_data in files
            }:

                # Already an absolute editor path.
                pass

            else:

                # CHANGED:
                # Do not claim an ambiguous basename is active.
                active_file = None

        # CHANGED:
        # Recalculate the active flag after resolving the
        # absolute active-file path.
        for file_data in files:

            file_data["active"] = (
                file_data["path"]
                == active_file
            )

        unsaved_changes = (
            self.capture_unsaved_changes(
                files
            )
        )

        for file_data in files:

            path = file_data["path"]

            if path in unsaved_changes:

                file_data["unsaved"] = True

                file_data["content"] = (
                    unsaved_changes[path]
                )

            else:

                file_data["unsaved"] = False

        if not files:
            active_file = None

        # CHANGED:
        # Preserve raw VS Code state in the snapshot.
        return Snapshot(

            application="vscode",

            workspace={
                "id": workspace[
                    "workspace_id"
                ],

                "path": workspace[
                    "workspace_path"
                ],
            },

            files=files,

            layout=layout,

            active_file=active_file,

            editor_state=(
                json.loads(
                    editor_state_raw
                )
                if editor_state_raw
                else None
            ),

            text_editor_state=(
                text_editor_state_raw
            ),

            # CHANGED:
            # Store the portable project tree in the snapshot.
            project=self.capture_project(
                self.normalize_workspace_path(
                    workspace[
                        "workspace_path"
                    ]
                ),
                files,
            ),
        )

    def restore(
        self,
        snapshot_data,
    ):

        if not snapshot_data:
            return False

        if snapshot_data.get(
            "application"
        ) != "vscode":

            print(
                "Snapshot is not a VS Code snapshot."
            )

            return False

        workspace = snapshot_data.get(
            "workspace"
        )

        if not workspace:

            print(
                "Snapshot does not contain a workspace."
            )

            return False

        source_workspace = workspace.get(
            "path"
        )

        if not source_workspace:

            print(
                "Snapshot does not contain a workspace path."
            )

            return False

        source_workspace = (
            self.normalize_workspace_path(
                source_workspace
            )
        )

        source_workspace = str(
            Path(
                source_workspace
            ).resolve()
        )

        # CHANGED:
        # Automatically map /home/<source-user>/... to the
        # equivalent location under the current user's home.
        destination_path = (
            self.map_workspace_to_current_home(
                source_workspace
            )
        )

        if destination_path is None:

            print(
                "Could not map the source workspace to "
                "the current user's home directory:"
            )

            print(
                f"  {source_workspace}"
            )

            return False

        destination_workspace = str(
            destination_path
        )

        files = snapshot_data.get(
            "files",
            [],
        )

        print(
            "Restoring VS Code workspace:"
        )

        print(
            f"  Path: "
            f"{destination_workspace}"
        )

        print(
            f"  Files: "
            f"{len(files)}"
        )

        print(
            f"  Groups: "
            f"{len(snapshot_data.get('layout', {}).get('groups', []))}"
        )

        print(
            f"  Active: "
            f"{snapshot_data.get('active_file')}"
        )

        # ======================================================
        # STEP 1
        # If the mapped project already exists, use it directly.
        # Otherwise recreate the project from the cloud snapshot.
        # ======================================================

        destination_path = Path(
            destination_workspace
        )

        if destination_path.exists():

            if not destination_path.is_dir():

                print(
                    "Destination workspace path exists "
                    "but is not a directory:"
                )

                print(
                    f"  {destination_workspace}"
                )

                return False

            print(
                "Destination project already exists. "
                "Using the existing project."
            )

        else:

            project = snapshot_data.get(
                "project"
            )

            if not project:

                print(
                    "Destination project does not exist "
                    "and the snapshot does not contain "
                    "project data."
                )

                return False

            print(
                "Destination project does not exist. "
                "Recreating project from cloud snapshot..."
            )

            if not self.restore_project(
                project,
                destination_workspace,
            ):

                print(
                    "Could not recreate "
                    "destination project."
                )

                return False

        # ======================================================
        # STEP 2
        # Start VS Code once so it creates the
        # destination workspace storage.
        # ======================================================

        print(
            "Preparing destination VS Code workspace..."
        )

        destination_storage = (
            self.prepare_destination_workspace(
                destination_workspace
            )
        )

        if not destination_storage:

            print(
                "Could not locate destination "
                "workspace storage."
            )

            return False

        # ======================================================
        # STEP 3
        # Close VS Code before modifying state.vscdb.
        # ======================================================

        print(
            "Closing VS Code before restoring editor state..."
        )

        if not self.close_vscode():
            return False

        # ======================================================
        # STEP 4
        # Locate destination storage again.
        # ======================================================

        destination_storage = (
            self.find_storage_by_path(
                destination_workspace
            )
        )

        if not destination_storage:

            print(
                "Destination workspace storage "
                "could not be found."
            )

            return False

        state_db = (
            destination_storage[
                "state_db"
            ]
        )

        print(
            "Restoring VS Code editor state..."
        )

        # ======================================================
        # STEP 5
        # Remap source paths to destination paths.
        # ======================================================

        snapshot_copy = json.loads(
            json.dumps(
                snapshot_data
            )
        )

        snapshot_copy = (
            self.remap_snapshot_paths(
                snapshot_copy,
                destination_workspace,
            )
        )

        # CHANGED:
        # Apply unsaved editor contents after mapping them
        # to the destination project path.
        self.restore_unsaved_files(
            snapshot_copy.get(
                "files",
                [],
            )
        )

        # ======================================================
        # STEP 6
        # Write raw VS Code state.
        # ======================================================

        if not self.restore_raw_state(
            state_db,
            snapshot_copy,
        ):

            print(
                "Could not restore VS Code state."
            )

            return False

        # ======================================================
        # STEP 7
        # Start VS Code again.
        # ======================================================

        print(
            "Starting restored VS Code workspace..."
        )

        self.launch_restored_workspace(
            destination_workspace
        )

        print(
            "VS Code workspace restored successfully."
        )

        return True