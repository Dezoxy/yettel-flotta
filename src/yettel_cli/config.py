from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_COOKIE_FILE, DEFAULT_EXPORT_DIR, DEFAULT_HISTORY_DB


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    env_file: Path
    cookie_file: Path
    export_dir: Path
    db_path: Path
    timeout_seconds: int = 30
    retries: int = 1
    debug_html_dir: Path | None = None

    @classmethod
    def from_values(
        cls,
        *,
        env_file: str | Path = ".env",
        cookie_file: str | Path | None = None,
        export_dir: str | Path | None = None,
        db_path: str | Path | None = None,
        project_root: Path | None = None,
    ) -> AppConfig:
        root = project_root or Path.cwd()
        env_path = Path(env_file).expanduser()
        load_dotenv(env_path)

        resolved_cookie_file = Path(
            cookie_file or os.environ.get("YETTEL_COOKIE_FILE") or root / DEFAULT_COOKIE_FILE
        ).expanduser()
        resolved_export_dir = Path(
            export_dir or os.environ.get("YETTEL_EXPORT_DIR") or root / DEFAULT_EXPORT_DIR
        ).expanduser()
        resolved_db_path = Path(
            db_path or os.environ.get("YETTEL_HISTORY_DB") or root / DEFAULT_HISTORY_DB
        ).expanduser()
        debug_html = os.environ.get("YETTEL_DEBUG_HTML_DIR")

        return cls(
            project_root=root,
            env_file=env_path,
            cookie_file=resolved_cookie_file,
            export_dir=resolved_export_dir,
            db_path=resolved_db_path,
            timeout_seconds=int(os.environ.get("YETTEL_TIMEOUT_SECONDS", "30")),
            retries=int(os.environ.get("YETTEL_RETRIES", "1")),
            debug_html_dir=Path(debug_html).expanduser() if debug_html else None,
        )


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)
