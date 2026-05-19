from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from yettel_cli.cli import main
from yettel_cli.models import UsageResult, UsageRow
from yettel_cli.output import render_usage_csv
from yettel_cli.storage import UsageHistoryStore


def sample_result() -> UsageResult:
    return UsageResult(
        phone="201234567",
        fetched_at=datetime.fromisoformat("2026-05-19T16:00:00+02:00"),
        rows=[
            UsageRow(
                name="EU roaming adatkeret",
                limit="102 GB",
                available="102 GB",
                valid_until="2026.06.06",
            )
        ],
    )


def test_render_usage_csv_includes_business_context() -> None:
    csv_text = render_usage_csv([sample_result()])

    assert csv_text.startswith("\ufeff")
    assert "phone,fetched_at,name,limit,available,valid_until" in csv_text
    assert "201234567" in csv_text
    assert "EU roaming adatkeret" in csv_text


def test_history_store_persists_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "history.sqlite3"
    count = UsageHistoryStore(db_path).save_result(sample_result())

    with sqlite3.connect(db_path) as connection:
        saved = connection.execute("SELECT phone, name, available FROM usage_history").fetchall()

    assert count == 1
    assert saved == [("201234567", "EU roaming adatkeret", "102 GB")]


def test_menu_can_exit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "7")

    assert main(["--env-file", str(tmp_path / ".env"), "--cookie-file", str(tmp_path / "cookies.txt")]) == 0


def test_menu_ctrl_c_exits_cleanly(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    def interrupt(_prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)

    assert main(["--env-file", str(tmp_path / ".env"), "--cookie-file", str(tmp_path / "cookies.txt")]) == 130
    assert "Exiting." in capsys.readouterr().out
