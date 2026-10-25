CURRENT_SNAPSHOT_VERSION = 5


def migrate_snapshot_data(data):
    """Validate and apply safe additive migrations to older snapshot payloads.

    Version 5 introduced browser_urls. Older payloads can be upgraded in memory
    without rewriting the cloud record. Future versions are rejected rather than
    silently restoring an unknown format.
    """
    if not isinstance(data, dict):
        raise ValueError("Snapshot payload must be a JSON object.")
    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("Snapshot version must be a positive integer.")
    if version > CURRENT_SNAPSHOT_VERSION:
        raise ValueError(
            f"Snapshot version {version} is newer than this Oryn client supports "
            f"(maximum {CURRENT_SNAPSHOT_VERSION}). Update Oryn before restoring it."
        )
    migrated = dict(data)
    integrity = migrated.get("_integrity")
    if integrity is not None:
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise ValueError("Snapshot integrity metadata is invalid.")
        expected_digest = integrity.get("digest")
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise ValueError("Snapshot integrity digest is invalid.")
        unsigned = dict(migrated)
        unsigned.pop("_integrity", None)
        canonical = __import__("json").dumps(
            unsigned, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        actual_digest = __import__("hashlib").sha256(canonical).hexdigest()
        if not __import__("hmac").compare_digest(expected_digest, actual_digest):
            raise ValueError(
                "Snapshot integrity check failed. The saved data may be corrupted."
            )
    if "browser_urls" not in migrated:
        migrated["browser_urls"] = []
    if not isinstance(migrated["browser_urls"], list):
        raise ValueError("Snapshot browser_urls must be a list.")
    if "files" in migrated and not isinstance(migrated["files"], list):
        raise ValueError("Snapshot files must be a list.")
    if "workspace" in migrated and not isinstance(migrated["workspace"], dict):
        raise ValueError("Snapshot workspace must be an object.")
    return migrated


class Snapshot:

    def __init__(
        self,
        application,
        workspace,
        files,
        layout,
        active_file,
        editor_state=None,
        text_editor_state=None,
        project=None,
        browser_urls=None,          # CHANGED
    ):
        # CHANGED:
        # Version 5 adds browser URL capture.
        self.version = 5

        self.application = application

        self.workspace = workspace

        self.files = files

        self.layout = layout

        self.active_file = active_file

        self.editor_state = editor_state

        self.text_editor_state = text_editor_state

        self.project = project

        # CHANGED:
        # URLs of browser tabs that were open when
        # this snapshot was captured.
        self.browser_urls = browser_urls or []

    def to_dict(self):
        return {
            "version": self.version,

            "application": self.application,

            "workspace": self.workspace,

            "files": self.files,

            "layout": self.layout,

            "active_file": self.active_file,

            "editor_state": self.editor_state,

            "text_editor_state": self.text_editor_state,

            "project": self.project,

            # CHANGED:
            # Store browser URLs as part of the snapshot.
            "browser_urls": self.browser_urls,
        }