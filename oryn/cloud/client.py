import copy
import gzip
import hashlib
import json
import os
import time
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


MAX_COMPRESSED_SNAPSHOT_BYTES = int(3.5 * 1024 * 1024)
MAX_UNCOMPRESSED_SNAPSHOT_BYTES = int(7.5 * 1024 * 1024)


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
        self.last_request_metrics = None

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

        started = time.perf_counter()
        with urllib.request.urlopen(
            request, timeout=self.timeout
        ) as response:
            raw = response.read()
            result = json.loads(raw.decode("utf-8"))
            self._record_request_metrics(
                "POST", url, started, response.status,
                response.headers.get("X-Oryn-Process-Time"), len(raw),
            )
            return result

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

        started = time.perf_counter()
        with urllib.request.urlopen(
            request, timeout=self.timeout
        ) as response:
            raw = response.read()
            result = json.loads(raw.decode("utf-8"))
            self._record_request_metrics(
                "POST", url, started, response.status,
                response.headers.get("X-Oryn-Process-Time"), len(raw),
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

        started = time.perf_counter()
        # GET requests are safe to retry once on transient network/server errors.
        # Mutating requests are deliberately never retried to avoid duplicate writes.
        for attempt in range(2):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout
                ) as response:
                    raw = response.read()
                    result = json.loads(raw.decode("utf-8"))
                    self._record_request_metrics(
                        method, url, started, response.status,
                        response.headers.get("X-Oryn-Process-Time"), len(raw),
                    )
                    return result
            except HTTPError as exc:
                if method != "GET" or exc.code not in (429, 502, 503, 504) or attempt == 1:
                    raise
            except URLError:
                if method != "GET" or attempt == 1:
                    raise
            time.sleep(0.35 * (attempt + 1))
        raise RuntimeError("Cloud request failed after bounded retries.")

    def _record_request_metrics(self, method, url, started, status, server_seconds, response_bytes):
        try:
            server_seconds = float(server_seconds) if server_seconds is not None else None
        except (TypeError, ValueError):
            server_seconds = None
        self.last_request_metrics = {
            "method": method,
            "path": urlsplit(url).path,
            "seconds": time.perf_counter() - started,
            "server_seconds": server_seconds,
            "status": status,
            "response_bytes": response_bytes,
        }

    # CHANGED:
    # Create an authenticated snapshot.
    def create_snapshot(
        self,
        workspace_id,
        snapshot,
    ):
        # Vercel rejects request bodies well below the API's 8 MiB decoded
        # limit. Keep a conservative compressed-body budget and leave enough
        # headroom for gateway/protocol differences.
        original_payload = copy.deepcopy(snapshot.to_dict())
        project = original_payload.get("project")
        project_files = (
            list(project.get("files") or [])
            if isinstance(project, dict) else []
        )
        existing_omitted = (
            list(project.get("omitted_files") or [])
            if isinstance(project, dict) else []
        )
        largest_first = sorted(
            project_files,
            key=lambda item: len(str(item.get("data") or "")),
            reverse=True,
        )

        def encode_payload(omitted_count):
            payload = copy.deepcopy(original_payload)
            current_project = payload.get("project")
            removed = largest_first[:omitted_count]
            if removed and isinstance(current_project, dict):
                removed_paths = {
                    str(item.get("path", "unknown")) for item in removed
                }
                current_project["files"] = [
                    item for item in project_files
                    if str(item.get("path", "unknown")) not in removed_paths
                ]
                current_project["omitted_files"] = sorted(
                    set(existing_omitted) | removed_paths
                )
            canonical = json.dumps(
                payload, separators=(",", ":"), ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            payload["_integrity"] = {
                "algorithm": "sha256",
                "digest": hashlib.sha256(canonical).hexdigest(),
            }
            raw_data = json.dumps(
                payload, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
            compressed = gzip.compress(raw_data, compresslevel=6, mtime=0)
            return payload, raw_data, compressed, removed

        payload, raw_data, data, removed = encode_payload(0)
        if (
            len(raw_data) > MAX_UNCOMPRESSED_SNAPSHOT_BYTES
            or len(data) > MAX_COMPRESSED_SNAPSHOT_BYTES
        ):
            if not project_files or not isinstance(project, dict):
                raise ValueError(
                    "This snapshot is too large to upload safely. Oryn could not "
                    "reduce the editor/browser state enough to fit the cloud upload "
                    "limit. Close very large editor buffers or reduce the captured "
                    "workspace state, then try again."
                )

            # Find the smallest number of project files to omit while retaining
            # all editor/session metadata. Largest files are removed first so the
            # fewest files possible are omitted to fit the hosting gateway limit.
            low, high = 1, len(largest_first)
            best = None
            while low <= high:
                middle = (low + high) // 2
                candidate = encode_payload(middle)
                _, candidate_raw, candidate_compressed, _ = candidate
                fits = (
                    len(candidate_raw) <= MAX_UNCOMPRESSED_SNAPSHOT_BYTES
                    and len(candidate_compressed) <= MAX_COMPRESSED_SNAPSHOT_BYTES
                )
                if fits:
                    best = candidate
                    high = middle - 1
                else:
                    low = middle + 1

            if best is None:
                raise ValueError(
                    "This snapshot is still too large even after excluding all "
                    "project files. Oryn kept your local workspace untouched and "
                    "did not upload a partial snapshot. Close very large editor "
                    "buffers or reduce the captured editor state, then try again."
                )
            payload, raw_data, data, removed = best

        content_encoding = "gzip" if len(raw_data) >= 1024 else None
        if content_encoding is None:
            data = raw_data

        url = (
            f"{self.base_url}"
            f"/workspaces/{workspace_id}"
            f"/snapshots"
        )
        result = self._request(
            url,
            data=data,
            method="POST",
            content_encoding=content_encoding,
        )
        if isinstance(result, dict):
            result["_client_capture"] = {
                "omitted_project_files": [
                    str(item.get("path", "unknown")) for item in removed
                ],
                "compressed_bytes": len(data),
                "uncompressed_bytes": len(raw_data),
                "project_files_included": len(
                    (payload.get("project") or {}).get("files") or []
                ) if isinstance(payload.get("project"), dict) else 0,
            }
        return result

    # CHANGED:
    # Retrieve authenticated snapshot.
    def get_snapshot(
        self,
        workspace_id,
        snapshot_id,
    ):
        from oryn.core.snapshot import migrate_snapshot_data

        url = (
            f"{self.base_url}"
            f"/workspaces/{workspace_id}"
            f"/snapshots/{snapshot_id}"
        )

        return migrate_snapshot_data(self._request(url))

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

    def rename_workspace(self, workspace_id, name):
        return self._request(
            f"{self.base_url}/workspaces/{workspace_id}",
            data=json.dumps({"name": name}).encode("utf-8"),
            method="PATCH",
        )

    def delete_workspace(self, workspace_id):
        return self._request(
            f"{self.base_url}/workspaces/{workspace_id}",
            method="DELETE",
        )

    def delete_snapshot(self, workspace_id, snapshot_id):
        return self._request(
            f"{self.base_url}/workspaces/{workspace_id}/snapshots/{snapshot_id}",
            method="DELETE",
        )


    def prune_snapshots(self, workspace_id, keep_last):
        return self._request(
            f"{self.base_url}/workspaces/{workspace_id}/snapshots/retention",
            data=json.dumps({"keep_last": keep_last}).encode("utf-8"),
            method="POST",
        )
