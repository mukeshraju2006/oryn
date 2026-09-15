import json
import urllib.request


class CloudClient:

    def __init__(
        self,
        base_url="http://127.0.0.1:8000",
        token=None,
    ):
        self.base_url = base_url.rstrip("/")

        # CHANGED:
        # Store authentication token.
        self.token = token

    # CHANGED:
    # Register a new Oryn user.
    def register(
        self,
        email,
        password,
    ):

        data = json.dumps(
            {
                "email": email,
                "password": password,
            }
        ).encode("utf-8")

        url = (
            f"{self.base_url}/auth/register"
        )

        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    # CHANGED:
    # Login and receive JWT.
    def login(
        self,
        email,
        password,
    ):

        data = json.dumps(
            {
                "email": email,
                "password": password,
            }
        ).encode("utf-8")

        url = (
            f"{self.base_url}/auth/login"
        )

        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(
            request
        ) as response:

            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        # CHANGED:
        # Save JWT for subsequent requests.
        self.token = result[
            "access_token"
        ]

        return result

    # CHANGED:
    # Create authenticated request.
    def _request(
        self,
        url,
        data=None,
        method="GET",
    ):

        headers = {}

        if data is not None:

            headers[
                "Content-Type"
            ] = "application/json"

        if self.token:

            headers[
                "Authorization"
            ] = f"Bearer {self.token}"

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        with urllib.request.urlopen(
            request
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    # CHANGED:
    # Create an authenticated snapshot.
    def create_snapshot(
        self,
        workspace_id,
        snapshot,
    ):

        data = json.dumps(
            snapshot.to_dict()
        ).encode("utf-8")

        url = (
            f"{self.base_url}"
            f"/workspaces/{workspace_id}"
            f"/snapshots"
        )

        return self._request(
            url,
            data=data,
            method="POST",
        )

    # CHANGED:
    # Retrieve authenticated snapshot.
    def get_snapshot(
        self,
        workspace_id,
        snapshot_id,
    ):

        url = (
            f"{self.base_url}"
            f"/workspaces/{workspace_id}"
            f"/snapshots/{snapshot_id}"
        )

        return self._request(
            url
        )

    # CHANGED:
    # List authenticated snapshots.
    def list_snapshots(
        self,
        workspace_id,
    ):

        url = (
            f"{self.base_url}"
            f"/workspaces/{workspace_id}"
            f"/snapshots"
        )

        return self._request(
            url
        )

    # CHANGED:
    # Create an authenticated workspace.
    def create_workspace(
        self,
        name,
    ):

        data = json.dumps(
            {
                "name": name,
            }
        ).encode("utf-8")

        url = (
            f"{self.base_url}/workspaces/"
        )

        return self._request(
            url,
            data=data,
            method="POST",
        )

    # CHANGED:
    # List authenticated workspaces.
    def list_workspaces(self):

        url = (
            f"{self.base_url}/workspaces/"
        )

        return self._request(
            url
        )