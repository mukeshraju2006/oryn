import getpass
import sys

from oryn.applications.vscode.adapter import VSCodeAdapter
from oryn.applications.browsers.adapter import BrowserAdapter  # CHANGED
from oryn.cloud.client import CloudClient
from oryn.cloud.session import load_token, save_token


def get_client():
    token = load_token()

    if not token:
        print("You are not logged in.")
        print("Run: python -m oryn.cli login")
        return None

    return CloudClient(token=token)


def login():
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    client = CloudClient()

    try:
        result = client.login(
            email,
            password,
        )

        save_token(
            result["access_token"]
        )

        print("Login successful.")

    except Exception as error:
        print(
            f"Login failed: {error}"
        )


def create_workspace():
    client = get_client()

    if not client:
        return

    name = input(
        "Workspace name: "
    ).strip()

    if not name:
        print(
            "Workspace name is required."
        )
        return

    try:
        workspace = client.create_workspace(
            name
        )

        print("Workspace created.")
        print(
            f"ID: {workspace['id']}"
        )
        print(
            f"Name: {workspace['name']}"
        )

    except Exception as error:
        print(
            f"Could not create workspace: {error}"
        )


def list_workspaces():
    client = get_client()

    if not client:
        return

    try:
        workspaces = client.list_workspaces()

        if not workspaces:
            print("No workspaces found.")
            return

        print("Oryn Workspaces")
        print("=" * 40)

        for workspace in workspaces:
            print(
                f"ID: {workspace['id']}"
            )
            print(
                f"Name: {workspace['name']}"
            )
            print("-" * 40)

    except Exception as error:
        print(
            f"Could not list workspaces: {error}"
        )


def capture():
    client = get_client()

    if not client:
        return

    try:
        workspaces = client.list_workspaces()

    except Exception as error:
        print(
            f"Could not retrieve workspaces: {error}"
        )
        return

    if not workspaces:
        print("No Oryn workspace exists.")
        print("Create one with:")
        print(
            "python -m oryn.cli create-workspace"
        )
        return

    workspace_id = workspaces[0]["id"]

    adapter = VSCodeAdapter()

    snapshot = adapter.capture()

    if not snapshot:
        print(
            "Could not capture current VS Code session."
        )
        return

    # CHANGED:
    # Capture URLs from browsers that are already open.
    # Oryn does not start the browser or use CDP during capture.
    browser_adapter = BrowserAdapter()
    browser_urls = browser_adapter.capture_urls()

    # CHANGED:
    # Attach the browser URLs to the existing snapshot
    # before uploading it to the cloud.
    snapshot.browser_urls = browser_urls

    print(
        f"Captured {len(browser_urls)} browser URL(s)."
    )

    try:
        result = client.create_snapshot(
            workspace_id,
            snapshot,
        )

        print(
            "Workspace captured successfully."
        )
        print(
            f"Workspace ID: {workspace_id}"
        )
        print(
            f"Snapshot ID: {result['id']}"
        )

    except Exception as error:
        print(
            f"Could not upload snapshot: {error}"
        )


def list_snapshots():
    client = get_client()

    if not client:
        return

    try:
        workspaces = client.list_workspaces()

        if not workspaces:
            print("No workspaces found.")
            return

        workspace_id = workspaces[0]["id"]

        snapshots = client.list_snapshots(
            workspace_id
        )

        if not snapshots:
            print("No snapshots found.")
            return

        print("Oryn Snapshots")
        print("=" * 40)

        for snapshot in snapshots:
            print(
                f"ID: {snapshot['id']}"
            )
            print(
                f"Version: {snapshot['version']}"
            )
            print(
                f"Created: {snapshot['created_at']}"
            )
            print("-" * 40)

    except Exception as error:
        print(
            f"Could not list snapshots: {error}"
        )


def restore(snapshot_id):
    client = get_client()

    if not client:
        return

    try:
        workspaces = client.list_workspaces()

        if not workspaces:
            print("No workspaces found.")
            return

        workspace_id = workspaces[0]["id"]

        snapshot = client.get_snapshot(
            workspace_id,
            snapshot_id,
        )

        adapter = VSCodeAdapter()

        # CHANGED:
        # Destination path is now determined automatically by
        # VSCodeAdapter from the source workspace path.
        success = adapter.restore(
            snapshot
        )

        if success:
            print(
                "Workspace restored successfully."
            )
        else:
            print(
                "Workspace restore failed."
            )

    except Exception as error:
        print(
            f"Could not restore snapshot: {error}"
        )


def main():
    if len(sys.argv) < 2:
        print("Oryn commands:")
        print("  python -m oryn.cli login")
        print(
            "  python -m oryn.cli create-workspace"
        )
        print(
            "  python -m oryn.cli workspaces"
        )
        print(
            "  python -m oryn.cli capture"
        )
        print(
            "  python -m oryn.cli snapshots"
        )
        print(
            "  python -m oryn.cli restore <snapshot_id>"
        )
        return

    command = sys.argv[1]

    if command == "login":
        login()

    elif command == "create-workspace":
        create_workspace()

    elif command == "workspaces":
        list_workspaces()

    elif command == "capture":
        capture()

    elif command == "snapshots":
        list_snapshots()

    elif command == "restore":
        if len(sys.argv) < 3:
            print(
                "Usage: python -m oryn.cli restore <snapshot_id>"
            )
            return

        try:
            snapshot_id = int(
                sys.argv[2]
            )

        except ValueError:
            print(
                "Snapshot ID must be an integer."
            )
            return

        # CHANGED:
        # No destination path is accepted or required.
        restore(snapshot_id)

    else:
        print(
            f"Unknown command: {command}"
        )


if __name__ == "__main__":
    main()