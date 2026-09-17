import json
import os
import sys
from pathlib import Path


# CHANGED: Keep the Linux location while using Windows per-user app data.
def get_session_file(
    platform_name=None,
    environ=None,
    home_path=None,
):
    platform_name = platform_name or sys.platform
    environ = os.environ if environ is None else environ
    home_path = Path.home() if home_path is None else Path(home_path)

    if platform_name.startswith("win"):
        appdata = environ.get("APPDATA")
        base_path = (
            Path(appdata)
            if appdata
            else home_path / "AppData" / "Roaming"
        )
        return base_path / "oryn" / "session.json"

    return home_path / ".config" / "oryn" / "session.json"


SESSION_FILE = get_session_file()


def save_token(token):

    SESSION_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    SESSION_FILE.write_text(
        json.dumps(
            {
                "access_token": token,
            }
        )
    )


def load_token():

    if not SESSION_FILE.exists():
        return None

    try:

        data = json.loads(
            SESSION_FILE.read_text()
        )

        return data.get(
            "access_token"
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None
