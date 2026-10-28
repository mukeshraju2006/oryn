import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


MAX_SNAPSHOT_REQUEST_BYTES = int(3.5 * 1024 * 1024)


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
            self.timeout = max(5.0, float(os.getenv("ORYN_REQUEST_TIMEOUT", "90")))
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
    # Create a complete authenticated snapshot. Large payloads are chunked;
    # project files are never pruned to fit an HTTP request limit.
    def create_snapshot(
        self,
        workspace_id,
        snapshot,
        progress=None,
    ):
        payload = snapshot.to_dict()
        canonical = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
        payload["_integrity"] = {
            "algorithm": "sha256",
            "digest": hashlib.sha256(canonical).hexdigest(),
        }
        raw_data = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")

        url = f"{self.base_url}/workspaces/{workspace_id}/snapshots"
        # CHANGED: Avoid a third full JSON serialization just to estimate
        # escaped size. Snapshot file bodies are base64 ASCII; a 20% margin
        # leaves room for Unicode-heavy metadata without another huge allocation.
        if len(raw_data) <= int(MAX_SNAPSHOT_REQUEST_BYTES * 0.8):
            result = self._request(url, data=raw_data, method="POST")
            request_count = 1
            upload_mode = "single-request"
        else:
            # CHANGED: Split bytes, not JSON objects, so Unicode and base64
            # file content survive exactly. The server verifies every chunk
            # and the complete payload before making a snapshot visible.
            chunk_bytes = 2 * 1024 * 1024  # CHANGED: fewer round trips for large snapshots
            upload_id = None
            chunk_count = (len(raw_data) + chunk_bytes - 1) // chunk_bytes
            if len(raw_data) > 256 * 1024 * 1024:
                raise ValueError(
                    "This workspace snapshot exceeds Oryn's current 256 MiB "
                    "cloud upload limit. No files were removed or uploaded as "
                    "a partial snapshot. Reduce the captured workspace size "
                    "or use a future release with larger-payload storage."
                )
            upload_digest = hashlib.sha256(raw_data).hexdigest()
            session = self._request(
                f"{self.base_url}/workspaces/{workspace_id}/snapshot-uploads",
                data=json.dumps({
                    "total_bytes": len(raw_data),
                    "chunk_count": chunk_count,
                    "sha256": upload_digest,
                }).encode("utf-8"),
                method="POST",
            )
            upload_id = session.get("upload_id")
            server_chunk_bytes = session.get("chunk_bytes")
            if (
                not isinstance(upload_id, str) or not upload_id
                or isinstance(server_chunk_bytes, bool)
                or not isinstance(server_chunk_bytes, int)
                or server_chunk_bytes != chunk_bytes
                or session.get("chunk_count") != chunk_count
                or session.get("total_bytes") != len(raw_data)
            ):
                raise RuntimeError(
                    "The server returned an invalid snapshot upload session. "
                    "No snapshot was finalized; update the desktop and cloud API together."
                )
            request_count = 1
            try:
                for index, offset in enumerate(range(0, len(raw_data), chunk_bytes)):
                    if progress is not None:
                        progress(
                            f"Uploading verified snapshot chunk {index + 1} of {chunk_count}…"
                        )
                    chunk = raw_data[offset:offset + chunk_bytes]
                    chunk_digest = hashlib.sha256(chunk).hexdigest()
                    chunk_payload = json.dumps({
                        "sha256": chunk_digest,
                        "data": base64.b64encode(chunk).decode("ascii"),
                    }, separators=(",", ":")).encode("utf-8")
                    chunk_url = (
                        f"{self.base_url}/workspaces/{workspace_id}"
                        f"/snapshot-uploads/{upload_id}/chunks/{index}"
                    )
                    last_error = None
                    for attempt in range(3):
                        try:
                            self._request(chunk_url, data=chunk_payload, method="PUT")
                            last_error = None
                            break
                        except HTTPError as error:
                            if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                                raise
                            last_error = error
                        except URLError as error:
                            if attempt == 2:
                                raise
                            last_error = error
                        time.sleep(0.4 * (attempt + 1))
                    if last_error is not None:
                        raise last_error
                    request_count += 1
            except Exception:
                # A failed chunk cannot produce a snapshot. Clean up staged
                # data; if cleanup fails, the server retains no visible snapshot.
                try:
                    self._request(
                        f"{self.base_url}/workspaces/{workspace_id}"
                        f"/snapshot-uploads/{upload_id}",
                        method="DELETE",
                    )
                except Exception:
                    pass
                raise

            # CHANGED: Finalize is safe to retry because the server retains an
            # idempotent receipt even if the first response was lost.
            if progress is not None:
                progress("Verifying every uploaded chunk and publishing snapshot…")
            finalize_url = (
                f"{self.base_url}/workspaces/{workspace_id}"
                f"/snapshot-uploads/{upload_id}/finalize"
            )
            last_error = None
            for attempt in range(3):
                try:
                    result = self._request(
                        finalize_url, data=b"{}", method="POST",
                    )
                    last_error = None
                    request_count += 1
                    break
                except HTTPError as error:
                    if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                        raise
                    last_error = error
                except URLError as error:
                    if attempt == 2:
                        raise
                    last_error = error
                time.sleep(0.4 * (attempt + 1))
            if last_error is not None:
                raise last_error
            upload_mode = "verified-chunked"

        if isinstance(result, dict):
            project = payload.get("project")
            result["_client_capture"] = {
                "omitted_project_files": [],
                "request_bytes": len(raw_data),
                "project_files_included": len(
                    (project or {}).get("files") or []
                ) if isinstance(project, dict) else 0,
                "excluded_project_files": list(
                    (project or {}).get("omitted_files") or []
                ) if isinstance(project, dict) else [],
                "exclusion_reasons": dict(
                    (project or {}).get("exclusion_reasons") or {}
                ) if isinstance(project, dict) else {},
                "upload_mode": upload_mode,
                "upload_requests": request_count,
                "verified_bytes": len(raw_data),
            }
        return result

    # CHANGED: Fetch editor state and a project hash manifest without transferring
    # every project file. Existing local projects can be checked before payload download.
    def get_restore_payload(self, workspace_id, snapshot_id, progress=None):
        from oryn.core.snapshot import migrate_snapshot_data

        if progress is not None:
            progress("Checking cloud snapshot and project manifest…")
        url = (
            f"{self.base_url}/workspaces/{workspace_id}"
            f"/snapshots/{snapshot_id}/restore-payload"
        )
        payload = self._request(url)
        if not isinstance(payload, dict):
            raise ValueError("Restore preview payload is not a JSON object.")
        manifest = payload.get("project_manifest", [])
        if not isinstance(manifest, list):
            raise ValueError("Restore preview returned an invalid project manifest.")
        # The server verifies the original integrity digest before removing file
        # contents. The reduced response is intentionally a different document.
        reduced = migrate_snapshot_data(payload)
        reduced["project_manifest"] = manifest
        return reduced

    # CHANGED:
    # Retrieve authenticated snapshot.
    def get_snapshot(
        self,
        workspace_id,
        snapshot_id,
        progress=None,
    ):
        from oryn.core.snapshot import migrate_snapshot_data

        # CHANGED: Probe size before downloading. A large snapshot must not
        # be returned as one giant response through a serverless gateway.
        manifest_url = (
            f"{self.base_url}/workspaces/{workspace_id}"
            f"/snapshots/{snapshot_id}/download-manifest"
        )
        if progress is not None:
            progress("Checking snapshot manifest and integrity metadata…")
        manifest = self._request(manifest_url)
        total_bytes = manifest.get("total_bytes")
        chunk_bytes = manifest.get("chunk_bytes")
        chunk_count = manifest.get("chunk_count")
        digest = manifest.get("sha256")
        if (
            isinstance(total_bytes, bool) or not isinstance(total_bytes, int)
            or total_bytes < 0 or total_bytes > 256 * 1024 * 1024
            or isinstance(chunk_bytes, bool) or not isinstance(chunk_bytes, int)
            or chunk_bytes <= 0
            or isinstance(chunk_count, bool) or not isinstance(chunk_count, int)
            or chunk_count != (total_bytes + chunk_bytes - 1) // chunk_bytes
            or not isinstance(digest, str) or len(digest) != 64
        ):
            raise ValueError("The server returned an invalid snapshot download manifest.")

        if total_bytes <= MAX_SNAPSHOT_REQUEST_BYTES:
            if progress is not None:
                progress("Downloading and validating saved snapshot…")
            url = (
                f"{self.base_url}/workspaces/{workspace_id}"
                f"/snapshots/{snapshot_id}"
            )
            payload = self._request(url)
            if not isinstance(payload, dict):
                raise ValueError("Downloaded snapshot is not a JSON object.")
            raw = json.dumps(
                payload, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
            if len(raw) != total_bytes:
                raise ValueError("Snapshot download byte count does not match the manifest.")
            if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
                raise ValueError("Snapshot download failed the full-payload checksum.")
            return migrate_snapshot_data(payload)

        chunks = []
        for index in range(chunk_count):
            if progress is not None:
                progress(
                    f"Downloading and verifying snapshot chunk {index + 1} of {chunk_count}…"
                )
            chunk_url = (
                f"{self.base_url}/workspaces/{workspace_id}"
                f"/snapshots/{snapshot_id}/download-chunks/{index}"
            )
            item = self._request(chunk_url)
            if item.get("snapshot_id") != snapshot_id or item.get("chunk_index") != index:
                raise ValueError(f"Snapshot download returned an unexpected chunk at index {index}.")
            try:
                chunk = base64.b64decode(item["data"], validate=True)
            except (KeyError, ValueError, base64.binascii.Error) as exc:
                raise ValueError(f"Snapshot download chunk {index} is not valid base64.") from exc
            if not hmac.compare_digest(
                hashlib.sha256(chunk).hexdigest(), str(item.get("sha256", ""))
            ):
                raise ValueError(f"Snapshot download chunk {index} failed checksum verification.")
            expected_size = min(chunk_bytes, total_bytes - index * chunk_bytes)
            if len(chunk) != expected_size:
                raise ValueError(f"Snapshot download chunk {index} has an unexpected size.")
            chunks.append(chunk)

        if progress is not None:
            progress("Checking complete snapshot checksum…")
        raw = b"".join(chunks)
        if len(raw) != total_bytes:
            raise ValueError("Snapshot download is incomplete: received byte count does not match.")
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
            raise ValueError("Snapshot download failed the full-payload checksum.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Downloaded snapshot is not valid UTF-8 JSON.") from exc
        return migrate_snapshot_data(payload)

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
