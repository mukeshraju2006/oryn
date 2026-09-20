import base64
import csv
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path, PurePosixPath, PureWindowsPath

from oryn.core.snapshot import Snapshot


class VSCodeNotFoundError(RuntimeError):
    pass


# CHANGED: Keep VS Code platform details in one small helper.
class VSCodePlatform:

    def __init__(
        self,
        platform_name=None,
        environ=None,
        which=None,
        home_path=None,
    ):
        self.platform_name = platform_name or sys.platform
        self.environ = os.environ if environ is None else environ
        self.which = shutil.which if which is None else which
        self.home_path = Path.home() if home_path is None else Path(home_path)

    @property
    def is_windows(self):
        return self.platform_name.startswith("win")

    def code_executable(self):
        names = ("code", "code.cmd") if self.is_windows else ("code",)

        for name in names:
            executable = self.which(name)
            if executable:
                return executable

        return None

    def code_user_data_path(self):
        if self.is_windows:
            appdata = self.environ.get("APPDATA")

            if appdata:
                return Path(appdata) / "Code"

            return self.home_path / "AppData" / "Roaming" / "Code"

        return self.home_path / ".config" / "Code"

    def workspace_storage_path(self):
        return (
            self.code_user_data_path()
            / "User"
            / "workspaceStorage"
        )

    def backups_path(self):
        return self.code_user_data_path() / "Backups"

    def vscode_process_ids(self):
        if self.is_windows:
            return self._windows_vscode_process_ids()

        return self._linux_vscode_process_ids()

    def _linux_vscode_process_ids(self):
        proc_path = Path("/proc")

        if not proc_path.is_dir():
            return [], "VS Code process inspection is unavailable on this system."

        process_ids = []

        for process_path in proc_path.iterdir():
            if not process_path.name.isdigit():
                continue

            try:
                process_name = (
                    process_path / "comm"
                ).read_text().strip()
            except OSError:
                continue

            if process_name == "code":
                process_ids.append(int(process_path.name))

        return process_ids, None

    def _windows_vscode_process_ids(self):
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FO",
                    "CSV",
                    "/NH",
                    "/FI",
                    "IMAGENAME eq Code.exe",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            return [], f"Could not inspect VS Code processes: {error}"

        if result.returncode != 0:
            return [], "Could not inspect VS Code processes with tasklist."

        process_ids = []

        for row in csv.reader(result.stdout.splitlines()):
            if len(row) < 2 or row[0].lower() != "code.exe":
                continue

            try:
                process_ids.append(int(row[1]))
            except ValueError:
                continue

        return process_ids, None

    def terminate_vscode(self):
        process_ids, error = self.vscode_process_ids()

        if error:
            return False, error

        if not process_ids:
            return True, None

        if self.is_windows:
            try:
                result = subprocess.run(
                    [
                        "taskkill",
                        "/IM",
                        "Code.exe",
                        "/T",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as terminate_error:
                return False, f"Could not close VS Code: {terminate_error}"

            if result.returncode != 0:
                return False, "Could not close VS Code with taskkill."

            return True, None

        for process_id in process_ids:
            try:
                os.kill(process_id, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except OSError as terminate_error:
                return False, f"Could not close VS Code: {terminate_error}"

        return True, None


class VSCodeAdapter:

    def __init__(self, platform=None):
        self.platform = platform or VSCodePlatform()

    def detect(self):
        process_ids, error = self.platform.vscode_process_ids()

        if error or not process_ids:
            return None

        return "\n".join(str(process_id) for process_id in process_ids)

    def _code_executable(self):
        executable = self.platform.code_executable()

        if executable:
            return executable

        raise VSCodeNotFoundError(
            "Could not find the VS Code command. "
            "Install VS Code and make its command-line launcher available on PATH."
        )

    def get_active_file(self):
        executable = self._code_executable()

        try:
            # CHANGED:
            # Explicitly decode VS Code --status as UTF-8 and replace
            # malformed bytes instead of using Windows' cp1252 default.
            result = subprocess.run(
                [
                    executable,
                    "--status",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            print(f"Could not query VS Code status: {error}")
            return None

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
        workspace_storage = self.platform.workspace_storage_path()

        if not workspace_storage.exists():
            return []

        workspaces = []

        for directory in workspace_storage.iterdir():
            if not directory.is_dir():
                continue

            state_db = directory / "state.vscdb"
            workspace_file = directory / "workspace.json"

            if (
                not state_db.exists()
                or not workspace_file.exists()
            ):
                continue

            try:
                workspace_data = json.loads(
                    workspace_file.read_text()
                )

                workspace_path = workspace_data.get(
                    "folder"
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
        workspaces = self.get_workspace_storages()

        if not workspaces:
            return None

        # CHANGED:
        # Normalize file:// workspace URIs before comparing paths.
        if workspace_path:
            target_path = self.normalize_workspace_path(
                workspace_path
            )

            for workspace in workspaces:
                stored_path = self.normalize_workspace_path(
                    workspace["workspace_path"]
                )

                if self._paths_equivalent(
                    stored_path,
                    target_path,
                ):
                    return workspace

        if active_file:
            # CHANGED:
            # Match parsed full editor resources instead of searching the
            # serialized database for a filename substring.
            active_path = self._snapshot_path(active_file)
            candidates = []

            for workspace in workspaces:
                editor_state = self.get_editor_state(
                    workspace["state_db"]
                )
                parsed = self.parse_editor_state(editor_state)
                if not parsed:
                    continue

                editor_paths = [
                    editor["path"]
                    for editor in parsed["editors"]
                    if editor.get("path")
                ]

                if active_path is not None:
                    exact = any(
                        self._paths_equivalent(
                            editor_path,
                            active_path,
                        )
                        for editor_path in editor_paths
                    )
                    if exact:
                        return workspace

                active_name = str(active_path or active_file).replace(
                    "\\", "/"
                ).rsplit("/", 1)[-1]
                if any(
                    str(editor_path).replace("\\", "/").rsplit("/", 1)[-1]
                    == active_name
                    for editor_path in editor_paths
                ):
                    candidates.append(workspace)

            if len(candidates) == 1:
                return candidates[0]

            if candidates:
                # CHANGED:
                # When --status supplies only a basename, prefer the
                # workspace whose folder name is reported as active, then
                # the most recently updated database. Never return the first
                # historical database with the same filename.
                active_folder = self._active_folder_name()
                if active_folder:
                    named = [
                        workspace
                        for workspace in candidates
                        if self._workspace_basename(
                            workspace["workspace_path"]
                        ).casefold()
                        == active_folder.casefold()
                    ]
                    if len(named) == 1:
                        return named[0]

                return max(
                    candidates,
                    key=lambda workspace: Path(
                        workspace["state_db"]
                    ).stat().st_mtime,
                )

        executable = self._code_executable()

        try:
            # CHANGED:
            # VS Code --status can contain bytes that Windows cp1252
            # cannot decode. Explicit UTF-8 decoding prevents capture
            # from failing in subprocess' reader thread.
            status = subprocess.run(
                [
                    executable,
                    "--status",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            status = None

        if status and status.returncode == 0:
            status_output = status.stdout

            for workspace in workspaces:
                stored_path = self.normalize_workspace_path(
                    workspace["workspace_path"]
                )

                if stored_path in status_output:
                    return workspace

        if len(workspaces) == 1:
            return workspaces[0]

        return None

    # CHANGED:
    # Read the active folder label from --status only as a basename
    # disambiguator; workspace paths are never taken from Process Argv.
    def _active_folder_name(self):
        executable = self._code_executable()
        try:
            # CHANGED:
            # Explicitly decode VS Code status output as UTF-8 so malformed
            # diagnostic bytes cannot terminate the capture operation.
            status = subprocess.run(
                [executable, "--status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            return None

        if status.returncode != 0:
            return None

        for line in status.stdout.splitlines():
            match = re.search(r"Folder \(([^)]+)\)", line.strip())
            if match:
                return match.group(1).strip()
        return None

    def _workspace_basename(self, workspace_path):
        parsed = self._snapshot_path(workspace_path)
        if parsed is None:
            return ""
        return parsed.name

    def get_editor_state(
        self,
        state_db,
    ):
        return self.read_state_value(
            state_db,
            "memento/workbench.parts.editor",
        )

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

                    for editor in node["data"].get(
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

                            resource = editor_data[
                                "resourceJSON"
                            ]

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
                "active_group": editor_part.get(
                    "activeGroup"
                ),
                "most_recent_active_groups": editor_part.get(
                    "mostRecentActiveGroups",
                    [],
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
        value = self.read_state_value(
            state_db,
            "memento/workbench.editors.files.textFileEditor",
        )

        if value is None:
            return None

        try:
            return json.loads(
                value
            )

        except json.JSONDecodeError:
            return None

    def read_state_value(
        self,
        state_db,
        key,
    ):
        try:
            database_uri = (
                Path(state_db)
                .resolve()
                .as_uri()
                + "?mode=ro"
            )

            with sqlite3.connect(
                database_uri,
                uri=True,
            ) as connection:
                row = connection.execute(
                    "SELECT value FROM ItemTable WHERE key = ?",
                    (key,),
                ).fetchone()

        except sqlite3.Error:
            return None

        if row is None:
            return None

        return row[0]

    def parse_text_editor_state(
        self,
        text_editor_state,
        open_editors,
    ):
        try:
            view_states = text_editor_state[
                "textEditorViewState"
            ]

            open_paths = {
                editor["path"]
                for editor in open_editors
            }

            result = {}

            for entry in view_states:
                file_uri, file_data = entry

                file_path = self.normalize_workspace_path(
                    file_uri
                )

                matching_open_path = next(
                    (
                        open_path
                        for open_path in open_paths
                        if self._paths_equivalent(
                            file_path,
                            open_path,
                        )
                    ),
                    None,
                )

                if matching_open_path is None:
                    continue

                per_group = result.setdefault(
                    matching_open_path,
                    {},
                )

                for (
                    group_id,
                    editor_state,
                ) in file_data.items():

                    cursor_states = editor_state.get(
                        "cursorState",
                        [],
                    )

                    view_state = editor_state.get(
                        "viewState",
                        {},
                    )

                    if not cursor_states:
                        continue

                    cursor = cursor_states[0]

                    position = cursor.get(
                        "position",
                        {},
                    )

                    selection_start = cursor.get(
                        "selectionStart",
                        {},
                    )

                    selection_end = cursor.get(
                        "selectionEnd",
                        {},
                    )

                    first_position = view_state.get(
                        "firstPosition",
                        {},
                    )

                    # CHANGED:
                    # Preserve editor state by group so the same file can
                    # exist in multiple groups without overwriting one
                    # another when the path matches exactly.
                    per_group[int(group_id)] = {
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
                                "line": selection_start.get(
                                    "lineNumber"
                                ),
                                "column": selection_start.get(
                                    "column"
                                ),
                            },
                            "end": {
                                "line": selection_end.get(
                                    "lineNumber"
                                ),
                                "column": selection_end.get(
                                    "column"
                                ),
                            },
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

    def find_unsaved_backup(
        self,
        file_path,
    ):
        backups_root = self.platform.backups_path()

        if not backups_root.exists():
            return None

        parsed_path = self._snapshot_path(file_path)

        if parsed_path is None or not parsed_path.is_absolute():
            return None

        file_uri = self._path_to_uri(parsed_path)

        for backup_directory in backups_root.iterdir():
            if not backup_directory.is_dir():
                continue

            file_directory = (
                backup_directory / "file"
            )

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

                        parts = first_line.split(
                            " ",
                            1,
                        )

                        if len(parts) != 2:
                            continue

                        backup_uri = parts[0]

                        if backup_uri != file_uri:
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

            backup = self.find_unsaved_backup(
                path
            )

            if backup:
                unsaved_changes[path] = backup["content"]

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
            ".angular"
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
                    relative.as_posix()
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

            for directory_name in directory_names:
                directory_path = (
                    current_path / directory_name
                )

                try:
                    relative = (
                        directory_path.relative_to(
                            workspace
                        )
                    )

                    directories.append(
                        relative.as_posix()
                    )

                except ValueError:
                    continue

            for file_name in sorted(
                file_names
            ):
                file_path = (
                    current_path / file_name
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

                    relative_string = relative.as_posix()

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
    # Parse snapshot paths using their own syntax rather than the
    # destination machine's filesystem rules.
    def _snapshot_path(self, value):
        if not isinstance(value, str) or not value:
            return None

        raw_path = value

        if value.startswith("file://"):
            parsed = urllib.parse.urlparse(value)
            raw_path = urllib.parse.unquote(
                parsed.path
            )

            if (
                parsed.netloc
                and parsed.netloc.lower() != "localhost"
            ):
                return PureWindowsPath(
                    "//" + parsed.netloc + raw_path
                )

            if re.match(
                r"^/[A-Za-z]:[\\/]",
                raw_path,
            ):
                raw_path = raw_path[1:]

        if (
            re.match(
                r"^[A-Za-z]:",
                raw_path,
            )
            or raw_path.startswith("\\\\")
            or raw_path.startswith("//")
            or "\\" in raw_path
        ):
            return PureWindowsPath(
                raw_path
            )

        return PurePosixPath(
            raw_path
        )

    def _relative_parts(
        self,
        path,
        root,
    ):
        if (
            path is None
            or root is None
            or type(path) is not type(root)
        ):
            return None

        path_parts = path.parts
        root_parts = root.parts

        if len(path_parts) < len(root_parts):
            return None

        if isinstance(
            path,
            PureWindowsPath,
        ):
            matches = all(
                path_part.casefold()
                == root_part.casefold()
                for path_part, root_part in zip(
                    path_parts,
                    root_parts,
                )
            )
        else:
            matches = (
                path_parts[
                    :len(root_parts)
                ]
                == root_parts
            )

        if not matches:
            return None

        return path_parts[
            len(root_parts):
        ]

    def _path_to_uri(
        self,
        path,
    ):
        value = str(path).replace(
            "\\",
            "/",
        )

        if value.startswith("//"):
            return (
                "file:"
                + urllib.parse.quote(
                    value,
                    safe="/:@",
                )
            )

        if re.match(
            r"^[A-Za-z]:/",
            value,
        ):
            value = "/" + value

        return (
            "file://"
            + urllib.parse.quote(
                value,
                safe="/:@",
            )
        )

    def _remap_path_value(
        self,
        value,
        source_root,
        destination_root,
    ):
        path = self._snapshot_path(
            value
        )
        source = self._snapshot_path(
            source_root
        )
        destination = self._snapshot_path(
            destination_root
        )

        relative_parts = self._relative_parts(
            path,
            source,
        )

        if (
            relative_parts is None
            or destination is None
        ):
            return value

        remapped = destination.joinpath(
            *relative_parts
        )

        if (
            isinstance(value, str)
            and value.startswith("file://")
        ):
            return self._path_to_uri(
                remapped
            )

        return str(remapped)

    def _paths_equivalent(
        self,
        first,
        second,
    ):
        first_path = self._snapshot_path(
            first
        )
        second_path = self._snapshot_path(
            second
        )

        if (
            first_path is None
            or second_path is None
        ):
            return False

        if type(first_path) is not type(
            second_path
        ):
            return False

        if isinstance(
            first_path,
            PureWindowsPath,
        ):
            return (
                str(first_path).casefold()
                == str(second_path).casefold()
            )

        return first_path == second_path

    def map_workspace_path(
        self,
        source_workspace,
        destination_home,
    ):
        source = self._snapshot_path(
            source_workspace
        )
        destination = self._snapshot_path(
            destination_home
        )

        if (
            source is None
            or destination is None
            or not destination.is_absolute()
        ):
            return None

        parts = source.parts

        if (
            isinstance(
                source,
                PurePosixPath,
            )
            and len(parts) >= 3
            and parts[0] == "/"
            and parts[1] == "home"
        ):
            relative_parts = parts[3:]

        elif (
            isinstance(
                source,
                PureWindowsPath,
            )
            and source.is_absolute()
            and len(parts) >= 4
            and parts[1].casefold() == "users"
        ):
            relative_parts = parts[3:]

        else:
            return None

        if any(
            part in (
                ".",
                "..",
            )
            for part in relative_parts
        ):
            return None

        return str(
            destination.joinpath(
                *relative_parts
            )
        )

    def map_workspace_to_current_home(
        self,
        source_workspace,
    ):
        destination = self.map_workspace_path(
            source_workspace,
            str(Path.home()),
        )

        return (
            Path(destination)
            if destination
            else None
        )

    def _portable_relative_parts(
        self,
        value,
    ):
        path = self._snapshot_path(
            value
        )

        if (
            path is None
            or path.is_absolute()
            or (
                isinstance(
                    path,
                    PureWindowsPath,
                )
                and path.drive
            )
        ):
            return None

        parts = tuple(
            part
            for part in path.parts
            if part not in (
                "",
                ".",
            )
        )

        if (
            not parts
            or any(
                part == ".."
                for part in parts
            )
        ):
            return None

        return parts

    def _safe_relative_destination(
        self,
        destination,
        relative_path,
    ):
        parts = self._portable_relative_parts(
            relative_path
        )

        if parts is None:
            return None

        target = destination.joinpath(
            *parts
        )

        if not self._is_path_within_directory(
            target,
            destination,
        ):
            return None

        return target

    # CHANGED:
    # Recreate a missing project from the cloud snapshot.
    def restore_project(
        self,
        project,
        destination_workspace,
    ):
        requested_destination = Path(
            destination_workspace
        )

        if not requested_destination.is_absolute():
            print(
                f"Destination workspace path must be absolute: "
                f"{destination_workspace}"
            )
            return False

        destination = requested_destination.resolve()

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        # CHANGED:
        # Double-check that destination directory was created successfully.
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
            target = self._safe_relative_destination(
                destination,
                relative_path,
            )

            if target is None:
                print(
                    f"Skipping unsafe project directory: "
                    f"{relative_path}"
                )
                continue

            try:
                target.mkdir(
                    parents=True,
                    exist_ok=True,
                )

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
            relative_path = file_data.get(
                "path"
            )

            encoded_data = file_data.get(
                "data"
            )

            if (
                not relative_path
                or encoded_data is None
            ):
                continue

            target = self._safe_relative_destination(
                destination,
                relative_path,
            )

            if target is None:
                print(
                    f"Skipping unsafe project path: "
                    f"{relative_path}"
                )
                continue

            try:
                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                if not self._is_path_within_directory(
                    target,
                    destination,
                ):
                    print(
                        f"Skipping unsafe project file "
                        f"(path traversal): "
                        f"{relative_path}"
                    )
                    continue

                raw_data = base64.b64decode(
                    encoded_data
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

    def _is_path_within_directory(
        self,
        path,
        directory,
    ):
        try:
            resolved_path = path.resolve()
            resolved_directory = directory.resolve()

            return resolved_path.is_relative_to(
                resolved_directory
            )

        except (
            ValueError,
            OSError,
        ):
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
            return self._remap_path_value(
                value,
                source_root,
                destination_root,
            )

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
                (
                    self._remap_path_value(
                        key,
                        source_root,
                        destination_root,
                    )
                    if isinstance(
                        key,
                        str,
                    )
                    else key
                ):
                    self.replace_paths(
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
            {}
        )

        source_workspace = workspace.get(
            "path"
        )

        if not source_workspace:
            return snapshot_data

        destination_root = str(
            destination_root
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

        if snapshot_data.get(
            "layout"
        ):
            snapshot_data[
                "layout"
            ] = self.replace_paths(
                snapshot_data[
                    "layout"
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
            for key in (
                "path",
                "uri",
            ):
                if file_data.get(key):
                    file_data[key] = (
                        self._remap_path_value(
                            file_data[key],
                            source_workspace,
                            destination_root,
                        )
                    )

        active_file = snapshot_data.get(
            "active_file"
        )

        if active_file:
            snapshot_data[
                "active_file"
            ] = self._remap_path_value(
                active_file,
                source_workspace,
                destination_root,
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
        workspace_path = (
            self.normalize_workspace_path(
                workspace_path
            )
        )

        for workspace in (
            self.get_workspace_storages()
        ):
            stored_path = workspace[
                "workspace_path"
            ]

            stored_path = (
                self.normalize_workspace_path(
                    stored_path
                )
            )

            if self._paths_equivalent(
                stored_path,
                workspace_path,
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

        text_editor_state = snapshot_data.get(
            "text_editor_state"
        )

        success = True

        if editor_state:
            if not self.write_state_value(
                state_db,
                "memento/"
                "workbench.parts.editor",
                editor_state,
            ):
                success = False

        if text_editor_state:
            if not self.write_state_value(
                state_db,
                "memento/"
                "workbench.editors.files."
                "textFileEditor",
                text_editor_state,
            ):
                success = False

        return success

    def normalize_workspace_path(
        self,
        workspace_path,
    ):
        path = self._snapshot_path(
            workspace_path
        )

        return (
            str(path)
            if path is not None
            else workspace_path
        )

    def restore_unsaved_files(
        self,
        files,
        destination_workspace,
    ):
        destination = Path(
            destination_workspace
        ).resolve()

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

            file_path = Path(path)

            if (
                not file_path.is_absolute()
                or not self._is_path_within_directory(
                    file_path,
                    destination,
                )
            ):
                print(
                    f"Skipping unsafe unsaved file path: {path}"
                )
                continue

            try:
                file_path = file_path.resolve()

                if not self._is_path_within_directory(
                    file_path,
                    destination,
                ):
                    print(
                        f"Skipping unsafe unsaved file path: {path}"
                    )
                    continue

                if file_path.exists():
                    backup_path = Path(
                        str(file_path)
                        + ".oryn-backup"
                    )

                    if not self._is_path_within_directory(
                        backup_path,
                        destination,
                    ):
                        print(
                            f"Skipping unsafe unsaved file path: {path}"
                        )
                        continue

                    backup_path.write_bytes(
                        file_path.read_bytes()
                    )

                file_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                if not self._is_path_within_directory(
                    file_path,
                    destination,
                ):
                    print(
                        f"Skipping unsafe unsaved file path: {path}"
                    )
                    continue

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
    # Launch VS Code only when destination workspace storage does
    # not already exist. This prevents opening another VS Code
    # instance when VS Code is already running.
    def prepare_destination_workspace(
        self,
        workspace_path,
    ):
        executable = self._code_executable()

        if not executable:
            return None

        # First check whether VS Code has already created storage
        # for this workspace.
        existing_storage = self.find_storage_by_path(
            workspace_path
        )

        if existing_storage:
            return existing_storage

        try:
            subprocess.Popen(
                [
                    executable,
                    workspace_path,
                ]
            )

        except OSError as error:
            print(
                f"Could not start VS Code: {error}"
            )
            return None

        # Wait for VS Code to create the workspace storage.
        deadline = time.monotonic() + 10

        while time.monotonic() < deadline:
            storage = self.find_storage_by_path(
                workspace_path
            )

            if storage:
                return storage

            time.sleep(0.25)

        print(
            "Timed out waiting for VS Code to create "
            "destination workspace storage."
        )

        return None

    # CHANGED:
    # Close VS Code and wait until all VS Code processes have
    # actually terminated before touching state.vscdb.
    def close_vscode(self):
        process_ids, error = (
            self.platform.vscode_process_ids()
        )

        if error:
            print(error)
            return False

        if not process_ids:
            return True

        success, error = (
            self.platform.terminate_vscode()
        )

        if not success:
            print(
                error
                or "Could not close VS Code."
            )
            return False

        # Do not rely on a fixed sleep.
        # VS Code can take different amounts of time to
        # shut down depending on its current state.
        deadline = time.monotonic() + 15

        while time.monotonic() < deadline:
            remaining_process_ids, inspection_error = (
                self.platform.vscode_process_ids()
            )

            if inspection_error:
                print(inspection_error)
                return False

            if not remaining_process_ids:
                # Give the operating system a short moment to
                # release file handles and SQLite locks.
                time.sleep(0.25)
                return True

            time.sleep(0.25)

        print(
            "Timed out waiting for VS Code to terminate."
        )

        return False

    # CHANGED:
    # Open VS Code after raw state has been restored.
    def launch_restored_workspace(
        self,
        workspace_path,
    ):
        executable = self._code_executable()

        if not executable:
            return False

        try:
            subprocess.Popen(
                [
                    executable,
                    workspace_path,
                ]
            )

        except OSError as error:
            print(
                f"Could not start VS Code: {error}"
            )
            return False

        return True

    def capture(self):
        active_file = self.get_active_file()

        workspace = self.find_workspace_storage(
            active_file=active_file,
        )

        if not workspace:
            return None

        editor_state_raw = self.get_editor_state(
            workspace["state_db"]
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
                editors = parsed_editor_state[
                    "editors"
                ]

                layout = parsed_editor_state[
                    "layout"
                ]

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

            group_state = parsed_text_editor_state.get(
                path,
                {},
            ).get(
                editor["group"],
                {},
            )

            if group_state:
                file_data.update(
                    group_state
                )

            file_data["group"] = editor[
                "group"
            ]

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
        # CHANGED:
        # Close any currently running VS Code BEFORE opening
        # the destination workspace or modifying VS Code state.
        # ======================================================

        print(
            "Checking for running VS Code processes..."
        )

        if not self.close_vscode():
            print(
                "Could not completely close VS Code "
                "before restore."
            )
            return False

        # ======================================================
        # STEP 3
        # Prepare destination workspace storage.
        #
        # If storage already exists, this does not launch
        # another VS Code instance.
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
        # STEP 4
        # Close VS Code again.
        #
        # This matters when prepare_destination_workspace()
        # had to temporarily launch VS Code to create the
        # workspace storage.
        # ======================================================

        print(
            "Closing VS Code before restoring editor state..."
        )

        if not self.close_vscode():
            return False

        # ======================================================
        # STEP 5
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
        # STEP 6
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
            ),
            destination_workspace,
        )

        # ======================================================
        # STEP 7
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
        # STEP 8
        # Start VS Code again.
        # ======================================================

        print(
            "Starting restored VS Code workspace..."
        )

        if not self.launch_restored_workspace(
            destination_workspace
        ):
            return False

        print(
            "VS Code workspace restored successfully."
        )

        return True