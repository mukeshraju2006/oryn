import json
from pathlib import Path


class SnapshotStorage:

    def __init__(self, base_path=".oryn"):
        self.base_path = Path(base_path)
        self.snapshots_path = self.base_path / "snapshots"

    def save(self, snapshot):
        self.snapshots_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        snapshot_file = (
            self.snapshots_path
            / "snapshot.json"
        )

        with snapshot_file.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                snapshot.to_dict(),
                file,
                indent=2,
            )

        return snapshot_file