"""Local credential persistence for the CLI (`platform login`).

The directory is overridable via EMINIDATABASE_CONFIG_DIR so tests (and anyone
running multiple isolated profiles) never touch a real home directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("EMINIDATABASE_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".eminidatabase"


def credentials_path() -> Path:
    return config_dir() / "credentials.json"


def save_credentials(base_url: str, email: str, token: str) -> None:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = credentials_path()
    path.write_text(json.dumps({"base_url": base_url, "email": email, "token": token}, indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort on platforms where chmod semantics differ (e.g. Windows)


def load_credentials() -> dict | None:
    path = credentials_path()
    if not path.exists():
        return None
    return json.loads(path.read_text())


def clear_credentials() -> None:
    path = credentials_path()
    if path.exists():
        path.unlink()
