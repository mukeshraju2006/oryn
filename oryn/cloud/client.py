import gzip
import json
import os
import urllib.request


class CloudClient:

    def __init__(
        self,
        base_url=None,
        token=None,
    ):
        # Allow deployments to override the API URL without changing the
        # desktop code. The default remains the existing configured host.
        self.base_url = (
            base_url
            or os.getenv("ORYN_API_URL")
            or "https://oryn-cloud-rebuild.vercel.app"
        ).rstrip("/")

        # Bound network waits so a stalled connection cannot leave the GUI
        # in a permanent loading state. Override for slower links with
        # ORYN_REQUEST_TIMEOUT (seconds).
        try:
            self.timeout = max(5.0, float(os.getenv("ORYN_REQUEST_TIMEOUT", "30")))
        except ValueError:
            self.timeout = 30.0

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
            request, timeout=self.timeout
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
            request, timeout=self.timeout
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
        content_encoding=None,
    ):

        headers = {}

        if data is not None:
            headers["Content-Type"] = "application/json"

        if content_encoding:
            headers["Content-Encoding"] = content_encoding

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
            request, timeout=self.timeout
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

        # Compact JSON avoids whitespace overhead. Gzip level 1 is fast and
        # substantially reduces text-heavy project snapshots over slow links.
        raw_data = json.dumps(
            snapshot.to_dict(),
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        content_encoding = None
        data = raw_data
        if len(raw_data) >= 1024:
            data = gzip.compress(raw_data, compresslevel=1, mtime=0)
            content_encoding = "gzip"

        url = (
            f"{self.base_url}"
            f"/workspaces/{workspace_id}"
            f"/snapshots"
        )

        return self._request(
            url,
            data=data,
            method="POST",
            content_encoding=content_encoding,
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