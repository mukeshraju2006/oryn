import os
import platform
import webbrowser
from pathlib import Path

from chromium_session import SessionParser


class BrowserAdapter:
    """
    Captures URLs from an already-running Google Chrome instance.

    Current MVP:
    - Linux
    - Windows
    - Google Chrome
    - Does not start Chrome during capture
    - Does not use CDP
    - Does not require a browser extension
    """

    # CHANGED:
    # Detect the Chrome profile directory based on the
    # operating system instead of assuming Linux.
    @staticmethod
    def get_chrome_profile():
        system = platform.system()

        if system == "Windows":
            local_app_data = os.environ.get(
                "LOCALAPPDATA"
            )

            if not local_app_data:
                return None

            return (
                Path(local_app_data)
                / "Google"
                / "Chrome"
                / "User Data"
                / "Default"
            )

        if system == "Linux":
            return (
                Path.home()
                / ".config"
                / "google-chrome"
                / "Default"
            )

        return None

    # CHANGED:
    # Resolve the Sessions directory dynamically for the
    # current operating system.
    @property
    def sessions_dir(self):
        profile = self.get_chrome_profile()

        if profile is None:
            return None

        return profile / "Sessions"

    def capture_urls(self):
        """
        Capture currently open HTTP/HTTPS URLs from Chrome.

        Chrome must already be running.

        Oryn does not:
        - start Chrome
        - use CDP
        - open a port
        - require an extension
        """

        sessions_dir = self.sessions_dir

        if sessions_dir is None:
            return []

        if not sessions_dir.exists():
            return []

        files = []

        # CHANGED:
        # Chrome can maintain multiple SNSS files.
        for pattern in (
            "Session_*",
            "Tabs_*",
            "Current Session",
            "Current Tabs",
        ):
            files.extend(
                sessions_dir.glob(pattern)
            )

        files = [
            path
            for path in files
            if path.is_file()
        ]

        if not files:
            return []

        files.sort(
            key=lambda path: path.stat().st_mtime
        )

        parser = SessionParser()

        for path in files:
            self._parse_file(
                parser,
                path
            )

        result = parser._build_result()

        return self._extract_urls(result)

    @staticmethod
    def _parse_file(parser, path):
        """
        Parse one SNSS file without resetting parser state.
        """

        try:
            data = path.read_bytes()
        except OSError:
            return

        if len(data) < 8:
            return

        if data[:4] != b"SNSS":
            return

        parser._buffer = data

        try:
            version = parser._read_uint32(4)
        except Exception:
            return

        if version not in (1, 3):
            return

        offset = 8

        while offset < len(data):
            try:
                if offset + 2 >= len(data):
                    break

                cmd_size = (
                    parser._read_uint16(offset)
                    - 1
                )

                offset += 2

                cmd_type = parser._read_uint8(
                    offset
                )

                offset += 1

                if offset + cmd_size > len(data):
                    break

                cmd_data = data[
                    offset:
                    offset + cmd_size
                ]

                parser._process_command(
                    cmd_type,
                    cmd_data,
                )

                offset += cmd_size

            except Exception:
                break

    @staticmethod
    def _extract_urls(result):
        """
        Extract URLs from non-deleted tabs.
        """

        urls = []

        for window in result.get(
            "windows",
            []
        ):
            if window.get("deleted"):
                continue

            for tab in window.get(
                "tabs",
                []
            ):
                if tab.get("deleted"):
                    continue

                url = tab.get("url")

                if not isinstance(url, str):
                    continue

                if not url.startswith(
                    (
                        "http://",
                        "https://",
                    )
                ):
                    continue

                if url not in urls:
                    urls.append(url)

        return urls

    def restore_urls(self, urls):
        """
        Open all saved browser URLs in the system
        default browser.

        The browser is only opened during restore.
        """

        if not urls:
            return 0

        opened = 0

        for url in urls:
            if not isinstance(url, str):
                continue

            if not url.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                continue

            try:
                webbrowser.open_new_tab(url)
                opened += 1
            except Exception:
                continue

        return opened