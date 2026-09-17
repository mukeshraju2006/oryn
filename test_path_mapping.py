#!/usr/bin/env python3
import base64
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oryn.applications.vscode.adapter import (
    VSCodeAdapter,
    VSCodeNotFoundError,
    VSCodePlatform,
)
from oryn.cloud.session import get_session_file


class VSCodePlatformTests(unittest.TestCase):

    def test_linux_executable_lookup(self):
        platform = VSCodePlatform(
            platform_name="linux",
            which=lambda name: "/usr/bin/code" if name == "code" else None,
        )

        self.assertEqual(platform.code_executable(), "/usr/bin/code")

    def test_windows_executable_lookup(self):
        platform = VSCodePlatform(
            platform_name="win32",
            which=lambda name: "C:/bin/code.cmd" if name == "code.cmd" else None,
        )

        self.assertEqual(platform.code_executable(), "C:/bin/code.cmd")

    def test_windows_prefers_code_when_available(self):
        platform = VSCodePlatform(
            platform_name="win32",
            which=lambda name: "C:/bin/code" if name == "code" else None,
        )

        self.assertEqual(platform.code_executable(), "C:/bin/code")

    def test_missing_executable(self):
        platform = VSCodePlatform(
            platform_name="linux",
            which=lambda name: None,
        )

        self.assertIsNone(platform.code_executable())

        with self.assertRaisesRegex(VSCodeNotFoundError, "VS Code command"):
            VSCodeAdapter(platform)._code_executable()

    def test_windows_process_detection_and_termination(self):
        platform = VSCodePlatform(platform_name="win32")
        tasklist_result = subprocess.CompletedProcess(
            ["tasklist"],
            0,
            '"Code.exe","1234","Console","1","10,000 K"\n',
            "",
        )
        taskkill_result = subprocess.CompletedProcess(
            ["taskkill"],
            0,
            "",
            "",
        )

        with patch(
            "oryn.applications.vscode.adapter.subprocess.run",
            side_effect=[tasklist_result, tasklist_result, taskkill_result],
        ) as run:
            self.assertEqual(platform.vscode_process_ids(), ([1234], None))
            self.assertEqual(platform.terminate_vscode(), (True, None))

        self.assertEqual(
            run.call_args_list[-1].args[0],
            ["taskkill", "/IM", "Code.exe", "/T"],
        )

    def test_adapter_detection_uses_platform_process_ids(self):
        class ProcessPlatform:
            def vscode_process_ids(self):
                return [41, 42], None

        self.assertEqual(VSCodeAdapter(ProcessPlatform()).detect(), "41\n42")

    def test_platform_storage_and_backup_locations(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            linux_home = Path(temporary_directory) / "linux-home"
            windows_appdata = Path(temporary_directory) / "appdata"

            linux = VSCodePlatform(
                platform_name="linux",
                home_path=linux_home,
            )
            self.assertEqual(
                linux.workspace_storage_path(),
                linux_home / ".config" / "Code" / "User" / "workspaceStorage",
            )
            self.assertEqual(
                linux.backups_path(),
                linux_home / ".config" / "Code" / "Backups",
            )

            windows = VSCodePlatform(
                platform_name="win32",
                environ={"APPDATA": str(windows_appdata)},
            )
            self.assertEqual(
                windows.workspace_storage_path(),
                windows_appdata / "Code" / "User" / "workspaceStorage",
            )
            self.assertEqual(
                windows.backups_path(),
                windows_appdata / "Code" / "Backups",
            )

    def test_session_locations(self):
        home = Path("/home/alice")
        self.assertEqual(
            get_session_file("linux", {}, home),
            home / ".config" / "oryn" / "session.json",
        )
        self.assertEqual(
            get_session_file("win32", {"APPDATA": "C:/Users/Alice/AppData/Roaming"}, home),
            Path("C:/Users/Alice/AppData/Roaming") / "oryn" / "session.json",
        )


class CrossPlatformPathTests(unittest.TestCase):

    def setUp(self):
        self.adapter = VSCodeAdapter()

    def test_uri_parsing_with_spaces(self):
        self.assertEqual(
            str(self.adapter._snapshot_path("file:///home/alice/my%20project")),
            "/home/alice/my project",
        )
        self.assertEqual(
            str(self.adapter._snapshot_path("file:///C:/Users/Alice/my%20project")),
            "C:\\Users\\Alice\\my project",
        )

    def test_home_mapping_all_platform_pairs(self):
        cases = [
            (
                "/home/alice/projects/oryn",
                "/home/bob",
                "/home/bob/projects/oryn",
            ),
            (
                "/home/alice/projects/oryn",
                "C:\\Users\\Bob",
                "C:\\Users\\Bob\\projects\\oryn",
            ),
            (
                "C:\\Users\\Alice\\projects\\oryn",
                "C:\\Users\\Bob",
                "C:\\Users\\Bob\\projects\\oryn",
            ),
            (
                "C:\\Users\\Alice\\projects\\oryn",
                "/home/bob",
                "/home/bob/projects/oryn",
            ),
        ]

        for source, destination_home, expected in cases:
            with self.subTest(source=source, destination_home=destination_home):
                self.assertEqual(
                    self.adapter.map_workspace_path(source, destination_home),
                    expected,
                )

    def test_home_mapping_rejects_source_traversal(self):
        self.assertIsNone(
            self.adapter.map_workspace_path(
                "/home/alice/project/../../outside",
                "/home/bob",
            )
        )

    def test_component_aware_remapping_for_paths_and_uris(self):
        snapshot = {
            "workspace": {"path": "/home/alice/project"},
            "active_file": "/home/alice/project/src/main.py",
            "files": [{
                "path": "/home/alice/project/src/main.py",
                "uri": "file:///home/alice/project/src/main.py",
            }],
            "layout": {
                "groups": [{"id": 0, "editors": ["/home/alice/project/src/main.py"]}],
                "active_group": 0,
                "most_recent_active_groups": [0],
            },
            "editor_state": {
                "path": "/home/alice/project/src/main.py",
                "uri": "file:///home/alice/project/src/main.py",
                "near_match": "/home/alice/project-old/main.py",
            },
            "text_editor_state": {
                "file:///home/alice/project/src/main.py": "state",
            },
        }

        remapped = self.adapter.remap_snapshot_paths(
            snapshot,
            "C:\\Users\\Bob\\project",
        )

        expected_path = "C:\\Users\\Bob\\project\\src\\main.py"
        self.assertEqual(remapped["active_file"], expected_path)
        self.assertEqual(remapped["files"][0]["path"], expected_path)
        self.assertEqual(
            remapped["files"][0]["uri"],
            "file:///C:/Users/Bob/project/src/main.py",
        )
        self.assertEqual(remapped["editor_state"]["near_match"], "/home/alice/project-old/main.py")
        self.assertEqual(
            remapped["layout"]["groups"][0]["editors"][0],
            expected_path,
        )
        self.assertIn(
            "file:///C:/Users/Bob/project/src/main.py",
            remapped["text_editor_state"],
        )

    def test_windows_to_linux_remapping(self):
        snapshot = {
            "workspace": {"path": "file:///C:/Users/Alice/project"},
            "active_file": "C:\\Users\\Alice\\project\\src\\main.py",
            "files": [{
                "path": "C:\\Users\\Alice\\project\\src\\main.py",
                "uri": "file:///C:/Users/Alice/project/src/main.py",
            }],
            "editor_state": {
                "path": "C:\\Users\\Alice\\project\\src\\main.py",
            },
            "text_editor_state": {
                "file:///C:/Users/Alice/project/src/main.py": "state",
            },
        }

        remapped = self.adapter.remap_snapshot_paths(snapshot, "/home/bob/project")
        self.assertEqual(remapped["active_file"], "/home/bob/project/src/main.py")
        self.assertEqual(remapped["files"][0]["uri"], "file:///home/bob/project/src/main.py")
        self.assertEqual(
            remapped["editor_state"]["path"],
            "/home/bob/project/src/main.py",
        )
        self.assertIn(
            "file:///home/bob/project/src/main.py",
            remapped["text_editor_state"],
        )

    def test_same_platform_remapping(self):
        linux_snapshot = {
            "workspace": {"path": "/home/alice/project"},
            "active_file": "/home/alice/project/src/main.py",
            "files": [],
        }
        windows_snapshot = {
            "workspace": {"path": "C:\\Users\\Alice\\project"},
            "active_file": "C:\\Users\\Alice\\project\\src\\main.py",
            "files": [],
        }

        self.assertEqual(
            self.adapter.remap_snapshot_paths(
                linux_snapshot,
                "/home/bob/project",
            )["active_file"],
            "/home/bob/project/src/main.py",
        )
        self.assertEqual(
            self.adapter.remap_snapshot_paths(
                windows_snapshot,
                "C:\\Users\\Bob\\project",
            )["active_file"],
            "C:\\Users\\Bob\\project\\src\\main.py",
        )


class RestoreSafetyTests(unittest.TestCase):

    def setUp(self):
        self.adapter = VSCodeAdapter()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "project"
        self.outside = Path(self.temporary_directory.name) / "outside.txt"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_windows_relative_project_paths_are_portable(self):
        project = {
            "directories": ["src"],
            "files": [{
                "path": "src\\main.py",
                "data": base64.b64encode(b"portable").decode("ascii"),
            }],
        }

        self.assertTrue(self.adapter.restore_project(project, self.root))
        self.assertEqual((self.root / "src" / "main.py").read_bytes(), b"portable")
        self.assertFalse((self.root / "src\\main.py").exists())

    def test_restore_project_rejects_traversal_and_absolute_paths(self):
        unsafe_paths = [
            "../../outside.txt",
            "../../../etc/file",
            "..\\..\\outside.txt",
            "C:\\outside.txt",
            "/absolute/path",
            "\\\\server\\share\\file",
            "src/../../outside.txt",
        ]
        project = {
            "directories": unsafe_paths,
            "files": [
                {
                    "path": path,
                    "data": base64.b64encode(b"unsafe").decode("ascii"),
                }
                for path in unsafe_paths
            ],
        }

        self.assertTrue(self.adapter.restore_project(project, self.root))
        self.assertFalse(self.outside.exists())
        self.assertFalse((self.root.parent / "etc" / "file").exists())

    def test_restore_project_rejects_symlink_escape(self):
        outside_directory = self.root.parent / "outside"
        outside_directory.mkdir()
        self.root.mkdir()

        try:
            os.symlink(outside_directory, self.root / "linked")
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks are unavailable in this environment")

        project = {
            "directories": [],
            "files": [{
                "path": "linked/escaped.txt",
                "data": base64.b64encode(b"unsafe").decode("ascii"),
            }],
        }

        self.assertTrue(self.adapter.restore_project(project, self.root))
        self.assertFalse((outside_directory / "escaped.txt").exists())

    def test_restore_unsaved_files_stays_within_workspace(self):
        self.root.mkdir()
        safe_file = self.root / "src" / "main.py"
        malicious_file = self.outside

        self.adapter.restore_unsaved_files(
            [
                {"path": str(safe_file), "content": "safe", "unsaved": True},
                {"path": str(malicious_file), "content": "unsafe", "unsaved": True},
                {"path": str(self.root / ".." / "outside-two.txt"), "content": "unsafe", "unsaved": True},
                {"path": "..\\..\\outside.txt", "content": "unsafe", "unsaved": True},
                {"path": "C:\\outside.txt", "content": "unsafe", "unsaved": True},
                {"path": "/absolute/path", "content": "unsafe", "unsaved": True},
                {"path": "\\\\server\\share\\file", "content": "unsafe", "unsaved": True},
            ],
            self.root,
        )

        self.assertEqual(safe_file.read_text(), "safe")
        self.assertFalse(malicious_file.exists())
        self.assertFalse((self.root.parent / "outside-two.txt").exists())


if __name__ == "__main__":
    unittest.main()
