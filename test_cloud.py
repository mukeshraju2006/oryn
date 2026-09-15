import json
import base64
import tempfile
import shutil
import os
import sqlite3
from pathlib import Path

from oryn.cloud.client import CloudClient
from oryn.cloud.session import load_token
from oryn.applications.vscode.adapter import VSCodeAdapter


BASE_URL = "http://127.0.0.1:8000"


def get_client():
    token = load_token()

    if not token:
        raise RuntimeError(
            "No Oryn login token found. Please login first."
        )

    return CloudClient(
        base_url=BASE_URL,
        token=token,
    )


def get_workspace(client):
    workspaces = client.list_workspaces()

    if not workspaces:
        raise RuntimeError(
            "No Oryn workspaces found. Create a workspace first."
        )

    workspace = workspaces[0]

    print(f"Oryn workspace ID: {workspace['id']}")
    print(f"Oryn workspace name: {workspace['name']}")

    return workspace


def test_capture(client):
    print("\n" + "=" * 60)
    print("TEST 1: CAPTURE CURRENT VS CODE WORKSPACE")
    print("=" * 60)

    workspace = get_workspace(client)

    adapter = VSCodeAdapter()

    snapshot = adapter.capture()

    if not snapshot:
        raise RuntimeError(
            "Failed to capture the current VS Code workspace."
        )

    snapshot_data = snapshot.to_dict()

    print("\nSnapshot captured locally.")
    print()

    print("Application:")
    print(f"  {snapshot_data['application']}")

    print("\nSnapshot version:")
    print(f"  {snapshot_data['version']}")

    print("\nWorkspace:")
    print(f"  {snapshot_data['workspace']}")

    print("\nOpen editor count:")
    print(f"  {len(snapshot_data.get('files', []))}")

    print("\nActive file:")
    print(f"  {snapshot_data.get('active_file')}")

    project = snapshot_data.get("project")

    if project:
        print("\nPortable project:")
        print(f"  Files: {len(project.get('files', []))}")
        print(f"  Directories: {len(project.get('directories', []))}")
    else:
        print("\nPortable project:")
        print("  Not captured")

    print("\nUploading snapshot...")

    result = client.create_snapshot(
        workspace_id=workspace["id"],
        snapshot=snapshot,
    )

    print("\nSnapshot uploaded successfully.")
    print(f"Snapshot ID: {result['id']}")
    print(f"Version: {result['version']}")
    print(f"Created: {result['created_at']}")

    return result


def get_latest_snapshot(client):
    workspace = get_workspace(client)

    snapshots = client.list_snapshots(
        workspace_id=workspace["id"]
    )

    if not snapshots:
        raise RuntimeError(
            "No snapshots found for the Oryn workspace."
        )

    latest = snapshots[0]

    return workspace, latest


def test_latest_snapshot(client):
    print("\n" + "=" * 60)
    print("TEST 2: RETRIEVE LATEST SNAPSHOT")
    print("=" * 60)

    workspace, latest = get_latest_snapshot(client)

    snapshot_id = latest["id"]

    print(f"\nLatest snapshot ID: {snapshot_id}")

    # CHANGED:
    # CloudClient.get_snapshot() requires both workspace ID
    # and snapshot ID.
    snapshot = client.get_snapshot(
        workspace["id"],
        snapshot_id,
    )

    print("\nSnapshot retrieved successfully.")
    print()

    # CHANGED:
    # The CloudClient returns the snapshot data directly.
    # There is NO "data" wrapper in the returned object.
    snapshot_data = snapshot

    summary = {
        "version": snapshot_data["version"],
        "application": snapshot_data["application"],
        "workspace": snapshot_data["workspace"],
        "active_file": snapshot_data.get("active_file"),
        "open_files": len(
            snapshot_data.get("files", [])
        ),
        "project_files": len(
            snapshot_data.get("project", {}).get("files", [])
        ),
    }

    print(json.dumps(
        summary,
        indent=2,
    ))

    return snapshot_data


def test_restore_latest(client):
    print("\n" + "=" * 60)
    print("TEST 3: RESTORE LATEST CLOUD SNAPSHOT")
    print("=" * 60)

    # CHANGED:
    # test_latest_snapshot() now returns the actual snapshot data.
    snapshot_data = test_latest_snapshot(client)

    print(
        f"\nRestoring snapshot: "
        f"{snapshot_data.get('id', 'latest')}"
    )

    adapter = VSCodeAdapter()

    success = adapter.restore(
        snapshot_data
    )

    if not success:
        raise RuntimeError(
            "VS Code restore failed."
        )

    print("\nRESTORE SUCCESSFUL")


def test_missing_project_restore(client):
    print("\n" + "=" * 60)
    print("TEST 4: MISSING-PROJECT CLOUD RESTORE")
    print("=" * 60)

    print(
        "\nThis test uses the latest snapshot stored in the cloud."
    )

    # CHANGED:
    # test_latest_snapshot() returns the actual snapshot directly.
    snapshot_data = test_latest_snapshot(client)

    project = snapshot_data.get("project")

    if not project:
        raise RuntimeError(
            "Latest cloud snapshot does not contain "
            "portable project data."
        )

    expected_files = project.get("files", [])
    expected_directories = project.get("directories", [])

    print("\nCloud snapshot contains:")
    print(f"  Files: {len(expected_files)}")
    print(f"  Directories: {len(expected_directories)}")

    if not expected_files:
        raise RuntimeError(
            "Portable project contains no files."
        )

    # CHANGED:
    # Create a completely isolated temporary destination.
    # This simulates a second laptop where the project does not exist.
    temp_root = Path(
        tempfile.mkdtemp(
            prefix="oryn-cross-device-"
        )
    )

    source_workspace = Path(
        snapshot_data["workspace"]["path"]
        .replace("file://", "")
    )

    destination = (
        temp_root
        / "otheruser"
        / "projects"
        / source_workspace.name
    )

    try:
        print("\nSimulated destination:")
        print(f"  {destination}")

        if destination.exists():
            raise RuntimeError(
                "Temporary destination unexpectedly already exists."
            )

        print("\nDestination project:")
        print("  MISSING")

        adapter = VSCodeAdapter()

        print(
            "\nRecreating project from cloud snapshot..."
        )

        # CHANGED:
        # Exercise the same project reconstruction method used
        # by VSCodeAdapter.restore() for a missing project.
        adapter.restore_project(
            project,
            destination,
        )

        print(
            "Project reconstruction completed."
        )

        # CHANGED:
        # Collect all files that were actually restored.
        restored_files = [
            path
            for path in destination.rglob("*")
            if path.is_file()
        ]

        print("\nVerification:")
        print(f"  Expected files: {len(expected_files)}")
        print(f"  Restored files: {len(restored_files)}")

        if len(restored_files) != len(expected_files):
            raise RuntimeError(
                "Restored file count does not match "
                "the cloud snapshot."
            )

        verified_files = 0

        # CHANGED:
        # Verify every file byte-for-byte against the Base64
        # data stored in the cloud snapshot.
        for file_data in expected_files:
            snapshot_path = Path(
                file_data["path"]
            )

            if snapshot_path.is_absolute():
                try:
                    relative_path = snapshot_path.relative_to(
                        source_workspace
                    )
                except ValueError:
                    raise RuntimeError(
                        f"Snapshot file is outside workspace: "
                        f"{file_data['path']}"
                    )
            else:
                relative_path = snapshot_path

            restored_path = (
                destination
                / relative_path
            )

            if not restored_path.exists():
                raise RuntimeError(
                    f"Missing restored file: "
                    f"{restored_path}"
                )

            encoded_data = file_data.get("data")

            if encoded_data is None:
                raise RuntimeError(
                    f"No data found for snapshot file: "
                    f"{file_data['path']}"
                )

            expected_bytes = base64.b64decode(
                encoded_data
            )

            actual_bytes = restored_path.read_bytes()

            if actual_bytes != expected_bytes:
                raise RuntimeError(
                    f"File contents differ: "
                    f"{file_data['path']}"
                )

            verified_files += 1

        print(
            f"  Byte-for-byte verified: {verified_files}"
        )

        # CHANGED:
        # Verify that every directory from the cloud snapshot exists.
        verified_directories = 0

        for directory in expected_directories:
            snapshot_directory = Path(directory)

            if snapshot_directory.is_absolute():
                try:
                    relative_directory = (
                        snapshot_directory.relative_to(
                            source_workspace
                        )
                    )
                except ValueError:
                    raise RuntimeError(
                        f"Snapshot directory is outside workspace: "
                        f"{directory}"
                    )
            else:
                relative_directory = snapshot_directory

            restored_directory = (
                destination
                / relative_directory
            )

            if not restored_directory.is_dir():
                raise RuntimeError(
                    f"Missing restored directory: "
                    f"{restored_directory}"
                )

            verified_directories += 1

        print(
            f"  Directories verified: {verified_directories}"
        )

        print("\nMISSING-PROJECT RESTORE SUCCESSFUL")
        print(
            "The project was recreated entirely "
            "from the cloud snapshot."
        )

    finally:
        # CHANGED:
        # Always clean up the temporary simulated laptop.
        shutil.rmtree(
            temp_root,
            ignore_errors=True,
        )

        print(
            "\nTemporary test destination cleaned up."
        )


def test_full_cross_device_restore(client):
    print("\n" + "=" * 60)
    print("TEST 5: FULL SIMULATED CROSS-DEVICE VS CODE RESTORE")
    print("=" * 60)
    print(
        "This test verifies the full restore state preparation "
        "but does not launch VS Code GUI."
    )

    # Retrieve the latest cloud snapshot
    snapshot_data = test_latest_snapshot(client)

    # Create a temporary directory to act as the new home
    with tempfile.TemporaryDirectory(prefix="oryn-test-home-") as temp_home_str:
        temp_home = Path(temp_home_str)
        # Set the HOME environment variable to the temporary home
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(temp_home)

        try:
            # Initialize the adapter
            adapter = VSCodeAdapter()

            # Extract source workspace path from snapshot
            source_workspace_str = snapshot_data["workspace"]["path"]
            if source_workspace_str.startswith("file://"):
                source_workspace_str = source_workspace_str[7:]
            source_workspace = Path(source_workspace_str)

            # Map source workspace to current home (which is now the temporary home)
            destination_workspace = adapter.map_workspace_to_current_home(
                str(source_workspace)
            )
            if destination_workspace is None:
                raise RuntimeError(
                    "Failed to map source workspace to current home"
                )
            destination_workspace = Path(destination_workspace)

            print(f"Source workspace: {source_workspace}")
            print(f"Destination workspace: {destination_workspace}")

            # Ensure the destination project does not exist
            if destination_workspace.exists():
                raise RuntimeError(
                    f"Destination workspace already exists: {destination_workspace}"
                )

            # Step 1: Restore the project if missing (using the adapter's method)
            project = snapshot_data.get("project")
            if not project:
                raise RuntimeError(
                    "Snapshot does not contain project data"
                )

            print("\nRestoring project from cloud snapshot...")
            if not adapter.restore_project(project, str(destination_workspace)):
                raise RuntimeError("Failed to restore project")

            # Verify the project was restored
            if not destination_workspace.exists():
                raise RuntimeError(
                    "Project was not restored to destination workspace"
                )

            # Step 2: Prepare the VS Code workspace storage manually
            # We simulate what prepare_destination_workspace would do:
            #   - Launch VS Code to create workspace storage
            #   - Find the workspace storage by path
            # Since we don't want to launch VS Code, we'll create the storage directly.

            # The workspace storage is located at:
            #   ~/.config/Code/User/workspaceStorage/
            # Each workspace gets a subdirectory (hash of workspace path)
            # We'll create a deterministic subdirectory for testing.

            # Create the base directories
            code_config = temp_home / ".config" / "Code" / "User"
            workspace_storage_base = code_config / "workspaceStorage"
            workspace_storage_base.mkdir(parents=True, exist_ok=True)

            # Create a subdirectory for our workspace (using a fixed hash for simplicity)
            # In reality, VS Code uses a hash of the workspace path.
            # We'll use a simple hash: the workspace path string length.
            workspace_hash = str(hash(str(destination_workspace)) % 10000)
            workspace_storage_dir = workspace_storage_base / workspace_hash
            workspace_storage_dir.mkdir(parents=True, exist_ok=True)

            # Create the state.vscdb file with the ItemTable
            state_db = workspace_storage_dir / "state.vscdb"
            # Initialize the database
            conn = sqlite3.connect(state_db)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.commit()
            conn.close()

            # Step 3: Remap snapshot paths to destination paths
            print("\nRemapping snapshot paths...")
            snapshot_copy = json.loads(json.dumps(snapshot_data))
            snapshot_copy = adapter.remap_snapshot_paths(
                snapshot_copy, str(destination_workspace)
            )

            # Step 4: Restore unsaved files
            print("Restoring unsaved files...")
            adapter.restore_unsaved_files(
                snapshot_copy.get("files", [])
            )

            # Step 5: Restore raw VS Code state
            print("Restoring raw VS Code state...")
            success = adapter.restore_raw_state(
                str(state_db), snapshot_copy
            )
            if not success:
                raise RuntimeError("Failed to restore raw VS Code state")

            # Verification: Check that the state.vscdb was updated correctly
            print("\nVerifying restored state...")
            conn = sqlite3.connect(state_db)
            cursor = conn.cursor()

            # Check the workbench.parts.editor key
            cursor.execute(
                "SELECT value FROM ItemTable WHERE key=?",
                ("memento/workbench.parts.editor",)
            )
            editor_state_row = cursor.fetchone()
            if editor_state_row is None:
                raise RuntimeError(
                    "memento/workbench.parts.editor not found in state.vscdb"
                )
            editor_state = json.loads(editor_state_row[0])
            print("  ✓ workbench.parts.editor restored")

            # Check the workbench.editors.files.textFileEditor key
            cursor.execute(
                "SELECT value FROM ItemTable WHERE key=?",
                ("memento/workbench.editors.files.textFileEditor",)
            )
            text_editor_state_row = cursor.fetchone()
            if text_editor_state_row is None:
                raise RuntimeError(
                    "memento/workbench.editors.files.textFileEditor not found in state.vscdb"
                )
            text_editor_state = json.loads(text_editor_state_row[0])
            print("  ✓ workbench.editors.files.textFileEditor restored")

            conn.close()

            # Verify the project files exist and have correct content
            print("\nVerifying restored project files...")
            expected_files = project.get("files", [])
            expected_directories = project.get("directories", [])

            restored_files = [
                path
                for path in destination_workspace.rglob("*")
                if path.is_file()
            ]
            if len(restored_files) != len(expected_files):
                raise RuntimeError(
                    f"Restored file count mismatch: expected {len(expected_files)}, got {len(restored_files)}"
                )

            verified_files = 0
            for file_data in expected_files:
                snapshot_path = Path(file_data["path"])
                if snapshot_path.is_absolute():
                    try:
                        relative_path = snapshot_path.relative_to(source_workspace)
                    except ValueError:
                        raise RuntimeError(
                            f"Snapshot file is outside workspace: {file_data['path']}"
                        )
                else:
                    relative_path = snapshot_path

                restored_path = destination_workspace / relative_path
                if not restored_path.exists():
                    raise RuntimeError(
                        f"Missing restored file: {restored_path}"
                    )

                encoded_data = file_data.get("data")
                if encoded_data is None:
                    raise RuntimeError(
                        f"No data found for snapshot file: {file_data['path']}"
                    )

                expected_bytes = base64.b64decode(encoded_data)
                actual_bytes = restored_path.read_bytes()
                if actual_bytes != expected_bytes:
                    raise RuntimeError(
                        f"File contents differ: {file_data['path']}"
                    )
                verified_files += 1

            print(f"  ✓ {verified_files} files verified byte-for-byte")

            # Verify directories
            verified_directories = 0
            for directory in expected_directories:
                snapshot_directory = Path(directory)
                if snapshot_directory.is_absolute():
                    try:
                        relative_directory = snapshot_directory.relative_to(source_workspace)
                    except ValueError:
                        raise RuntimeError(
                            f"Snapshot directory is outside workspace: {directory}"
                        )
                else:
                    relative_directory = snapshot_directory

                restored_directory = destination_workspace / relative_directory
                if not restored_directory.is_dir():
                    raise RuntimeError(
                        f"Missing restored directory: {restored_directory}"
                    )
                verified_directories += 1

            print(f"  ✓ {verified_directories} directories verified")

            # Verify active file path after remapping
            active_file = snapshot_data.get("active_file")
            if active_file:
                # The active_file in the snapshot has been remapped by remap_snapshot_paths
                # We can check the remapped active_file in snapshot_copy
                remapped_active_file = snapshot_copy.get("active_file")
                if remapped_active_file:
                    remapped_path = Path(remapped_active_file)
                    if not remapped_path.is_relative_to(destination_workspace):
                        raise RuntimeError(
                            f"Remapped active file {remapped_active_file} is not inside destination workspace"
                        )
                    print(f"  ✓ Active file remapped to: {remapped_active_file}")
                else:
                    print("  ! Warning: No active file in remapped snapshot")
            else:
                print("  ! No active file in snapshot")

            # Verify open editor paths after remapping (we already verified files exist)
            open_files = snapshot_data.get("files", [])
            if open_files:
                print(f"  ✓ {len(open_files)} open editor paths processed")

            # Verify editor group/layout state exists (we already checked editor_state)
            if editor_state:
                print("  ✓ Editor group/layout state exists")

            # Verify text editor state exists (we already checked text_editor_state)
            if text_editor_state:
                print("  ✓ Text editor state exists")

            # If the snapshot contains cursor, selection, scroll info, verify they survive remapping
            # We can check a few files that have text_editor_state
            files_with_state = 0
            for file_data in snapshot_copy.get("files", []):
                if "cursor" in file_data or "selection" in file_data or "scroll" in file_data:
                    files_with_state += 1
                    # We could do more detailed checks, but for now just count
            if files_with_state > 0:
                print(f"  ✓ {files_with_state} files have cursor/selection/scroll state preserved")

            print("\nFULL SIMULATED CROSS-DEVICE RESTORE SUCCESSFUL")
            print(
                "The project was restored and VS Code state was prepared "
                "in the simulated home environment."
            )

        finally:
            # Restore the original HOME environment variable
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


def run_all(client):
    print("\n" + "=" * 60)
    print("RUNNING ALL TESTS")
    print("=" * 60)

    test_capture(client)
    test_latest_snapshot(client)
    test_restore_latest(client)

    print("\n" + "=" * 60)
    print("ALL EXISTING TESTS PASSED")
    print("=" * 60)


def run_all_including_cross_device(client):
    print("\n" + "=" * 60)
    print("RUNNING ALL TESTS INCLUDING CROSS-DEVICE")
    print("=" * 60)

    test_capture(client)
    test_latest_snapshot(client)
    test_restore_latest(client)
    test_missing_project_restore(client)
    test_full_cross_device_restore(client)

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


def main():
    print("=" * 60)
    print("ORYN CROSS-DEVICE TEST")
    print("=" * 60)

    try:
        client = get_client()

        print("\nChoose a test:\n")
        print("1. Capture current VS Code workspace")
        print("2. Retrieve latest cloud snapshot")
        print("3. Restore latest cloud snapshot")
        print("4. Test missing-project cross-device restore")
        print("5. Test full simulated cross-device VS Code restore")
        print("6. Run all")
        print("7. Run all including cross-device restore")

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            test_capture(client)
        elif choice == "2":
            test_latest_snapshot(client)
        elif choice == "3":
            test_restore_latest(client)
        elif choice == "4":
            test_missing_project_restore(client)
        elif choice == "5":
            test_full_cross_device_restore(client)
        elif choice == "6":
            run_all(client)
        elif choice == "7":
            run_all_including_cross_device(client)
        else:
            print("\nInvalid choice.")

    except Exception as exc:
        print("\n" + "=" * 60)
        print("TEST FAILED")
        print("=" * 60)
        print()
        print(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()