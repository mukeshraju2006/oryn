import json
from pathlib import Path


SESSION_FILE = (
    Path.home()
    / ".config"
    / "oryn"
    / "session.json"
)


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