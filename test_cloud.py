import json
import base64
import tempfile
import shutil
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

    # CHANGED:
    # Include the missing-project restoration test.
    test_capture(client)
    test_latest_snapshot(client)
    test_restore_latest(client)
    test_missing_project_restore(client)

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
        print("4. Run all")
        print("5. Test missing-project cross-device restore")
        print("6. Run all including cross-device restore")

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            test_capture(client)

        elif choice == "2":
            test_latest_snapshot(client)

        elif choice == "3":
            test_restore_latest(client)

        elif choice == "4":
            run_all(client)

        # CHANGED:
        # Added dedicated missing-project test.
        elif choice == "5":
            test_missing_project_restore(client)

        # CHANGED:
        # Added complete test suite including cross-device test.
        elif choice == "6":
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