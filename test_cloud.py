from oryn.cloud.client import CloudClient
from oryn.cloud.session import load_token


token = load_token()

if not token:
    print("Not logged in.")
    exit()

client = CloudClient(token=token)

workspaces = client.list_workspaces()

if not workspaces:
    print("No workspaces found.")
    exit()

workspace_id = workspaces[0]["id"]

snapshots = client.list_snapshots(workspace_id)

if not snapshots:
    print("No snapshots found.")
    exit()

snapshot_id = snapshots[0]["id"]

snapshot = client.get_snapshot(
    workspace_id,
    snapshot_id
)

print("Snapshot:")
print(snapshot)

print("\nBrowser URLs:")
print("=" * 50)

for url in snapshot.get("browser_urls", []):
    print(url)