"""Per-user configuration, portable mode, and filesystem locations.

Windows uses ``%APPDATA%\\KiCadLibGen`` (settings/token) and
``%LOCALAPPDATA%\\KiCadLibGen\\logs``.  Linux uses
``${XDG_CONFIG_HOME:-~/.config}/kicad-lib-gen`` and
``${XDG_STATE_HOME:-~/.local/state}/kicad-lib-gen/logs``.  Portable mode
puts everything under ``data\\`` beside the executable.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
SEARCH_LIMITS = (10, 25, 50)
DEFAULT_SEARCH_LIMIT = 25
DEFAULT_HTTP_TIMEOUT = 30
DEFAULT_BATCH_DELAY_MS = 250
MAX_RECENT_DATABASES = 8

_SYNC_MARKERS = (
    ("onedrive", "OneDrive"),
    ("dropbox", "Dropbox"),
    ("google drive", "Google Drive"),
    ("googledrive", "Google Drive"),
    ("icloud", "iCloud Drive"),
    ("sharepoint", "SharePoint"),
    ("box sync", "Box"),
    ("pcloud", "pCloud"),
    ("mega", "MEGA"),
)


def platform_name() -> str:
    """``"windows"`` or ``"linux"`` (monkeypatchable in tests)."""
    return "windows" if os.name == "nt" else "linux"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Directory containing the executable (or the repo root in source runs)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def portable_marker_present() -> bool:
    return (app_dir() / "portable.txt").exists()


def resolve_portable(portable: bool | None = None) -> bool:
    if portable is not None:
        return portable
    env = os.environ.get("KICAD_LIB_GEN_PORTABLE", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    return portable_marker_present()


def config_dir(portable: bool | None = None) -> Path:
    override = os.environ.get("KICAD_LIB_GEN_CONFIG_DIR")
    if override:
        return Path(override)
    if resolve_portable(portable):
        return app_dir() / "data"
    if platform_name() == "windows":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / "KiCadLibGen"
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "kicad-lib-gen"


def log_dir(portable: bool | None = None) -> Path:
    override = os.environ.get("KICAD_LIB_GEN_LOG_DIR")
    if override:
        return Path(override)
    if resolve_portable(portable):
        return app_dir() / "data" / "logs"
    if platform_name() == "windows":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "KiCadLibGen" / "logs"
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "kicad-lib-gen" / "logs"


def settings_path(portable: bool | None = None) -> Path:
    return config_dir(portable) / "settings.json"


def default_token_path(portable: bool | None = None) -> Path:
    return config_dir(portable) / "token.json"


def default_database_path(portable: bool | None = None) -> Path:
    """Suggested local database path (never inside a sync folder)."""
    if resolve_portable(portable):
        return app_dir() / "data" / "components.db"
    return Path.home() / "KiCadLibGen" / "components.db"


def legacy_token_candidates() -> list[Path]:
    candidates = [app_dir() / ".token", Path.cwd() / ".token"]
    seen: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.append(resolved)
    return seen


def sync_folder_name(path: str | Path) -> str | None:
    """Return the sync product name if *path* sits inside a sync folder."""
    try:
        text = str(Path(path).expanduser().resolve()).replace("\\", "/").lower()
    except OSError:
        text = str(path).replace("\\", "/").lower()
    for marker, label in _SYNC_MARKERS:
        if marker in text:
            return label
    return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


@dataclass
class Settings:
    """User preferences persisted as JSON."""

    database_path: str = field(default_factory=lambda: str(default_database_path()))
    token_path: str = field(default_factory=lambda: str(default_token_path()))
    search_limit: int = DEFAULT_SEARCH_LIMIT
    http_timeout: int = DEFAULT_HTTP_TIMEOUT
    batch_delay_ms: int = DEFAULT_BATCH_DELAY_MS
    log_level: str = "INFO"
    recent_databases: list[str] = field(default_factory=list)
    portable: bool = False

    #: Absolute path this instance was loaded from (not serialised).
    source_path: Path | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        self.normalise()

    def normalise(self) -> None:
        if self.search_limit not in SEARCH_LIMITS:
            self.search_limit = min(SEARCH_LIMITS, key=lambda value: abs(value - self.search_limit))
        self.http_timeout = max(5, min(300, int(self.http_timeout)))
        self.batch_delay_ms = max(0, min(10000, int(self.batch_delay_ms)))
        if self.log_level not in LOG_LEVELS:
            self.log_level = "INFO"
        self.recent_databases = [str(item) for item in self.recent_databases][:MAX_RECENT_DATABASES]

    # -- persistence -----------------------------------------------------

    @classmethod
    def load(cls, *, portable: bool | None = None, path: str | Path | None = None) -> Settings:
        portable_value = resolve_portable(portable)
        source = Path(path) if path else settings_path(portable_value)
        data: dict[str, Any] = {}
        try:
            if source.exists():
                with source.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}

        allowed = {item.name for item in fields(cls)} - {"source_path"}
        values = {key: value for key, value in data.items() if key in allowed}
        values["portable"] = portable_value
        settings = cls(**values)
        settings.source_path = source
        return settings

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("source_path", None)
        return data

    def save(self) -> Path:
        destination = self.source_path or settings_path(self.portable)
        try:
            _atomic_write(
                destination, json.dumps(self.to_dict(), indent=2) + "\n"
            )
        except OSError:
            # A read-only config directory must not crash the app.
            pass
        self.source_path = destination
        return destination

    # -- helpers ---------------------------------------------------------

    def add_recent(self, path: str | Path) -> None:
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = str(path)
        self.recent_databases = [
            item for item in self.recent_databases if item != resolved
        ]
        self.recent_databases.insert(0, resolved)
        self.recent_databases = self.recent_databases[:MAX_RECENT_DATABASES]
        self.database_path = resolved

    @property
    def token_status_path(self) -> Path:
        return Path(self.token_path)

    @property
    def config_folder(self) -> Path:
        return self.source_path.parent if self.source_path else config_dir(self.portable)
