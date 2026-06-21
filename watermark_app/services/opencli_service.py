import os
import shutil
import subprocess
import uuid
import urllib.parse
import ipaddress
from pathlib import Path

CHROME_CANDIDATES_WIN = [
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
]


class OpenCliService:
    def __init__(self, chrome_path: str | None = None):
        self.chrome_path = chrome_path or self._find_chrome()
        self._temp_dirs: list[Path] = []

    def fetch_images_from_url(self, url: str) -> list[Path]:
        if not self._validate_url(url):
            return []
        if not self.chrome_path:
            return []
        # Stub: returns empty list when opencli not available
        return []

    def cleanup(self) -> None:
        for d in self._temp_dirs:
            self._cleanup_temp_dir(d)
        self._temp_dirs.clear()

    def _validate_url(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            if not parsed.hostname:
                return False
            # If hostname is an IP address, reject private/loopback/link-local
            try:
                addr = ipaddress.ip_address(parsed.hostname)
                if addr.is_private or addr.is_loopback or addr.is_link_local:
                    return False
            except ValueError:
                pass  # Domain name — cannot validate IP range, allow it
            return True
        except Exception:
            return False

    def _find_chrome(self) -> str | None:
        for var in ("CHROME_PATH", "WATERMARK_CHROME_PATH"):
            val = os.getenv(var)
            if val and Path(val).exists():
                return val
        candidates = CHROME_CANDIDATES_WIN if os.name == "nt" else []
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    @staticmethod
    def _cleanup_temp_dir(path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
