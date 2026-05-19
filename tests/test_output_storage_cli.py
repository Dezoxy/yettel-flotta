from __future__ import annotations

import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from yettel_cli.cli import main
from yettel_cli.config import AppConfig
from yettel_cli.models import UsageResult, UsageRow
from yettel_cli.output import export_usage_results, render_usage_csv
from yettel_cli.report import build_business_report
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


def test_history_store_returns_latest_result(tmp_path: Path) -> None:
    db_path = tmp_path / "history.sqlite3"
    store = UsageHistoryStore(db_path)
    store.save_result(sample_result())

    latest = store.latest_result("201234567")

    assert latest is not None
    assert latest.phone == "201234567"
    assert latest.rows[0].available == "102 GB"


def test_business_report_tracks_changes(tmp_path: Path) -> None:
    previous = sample_result()
    current = UsageResult(
        phone="201234567",
        fetched_at=datetime.fromisoformat("2026-05-19T17:00:00+02:00"),
        rows=[
            UsageRow(
                name="EU roaming adatkeret",
                limit="102 GB",
                available="98 GB",
                valid_until="2026.06.06",
            )
        ],
    )
    config = type(
        "Config",
        (),
        {
            "low_data_gb_threshold": 5.0,
            "expiry_warning_days": 3,
        },
    )()

    report = build_business_report([current], {"201234567": previous}, config)

    assert report.changes[0].previous_available == "102 GB"
    assert report.changes[0].current_available == "98 GB"
    assert report.changes[0].delta == "-4 GB"


def test_export_xlsx_creates_office_workbook(tmp_path: Path) -> None:
    path = export_usage_results([sample_result()], tmp_path, "xlsx")

    with zipfile.ZipFile(path) as workbook:
        names = set(workbook.namelist())
        usage_xml = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")

    assert path.suffix == ".xlsx"
    assert "xl/workbook.xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "EU roaming adatkeret" in usage_xml


def test_config_loads_business_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("YETTEL_DEFAULT_FORMAT", raising=False)
    monkeypatch.delenv("YETTEL_EXPORT_OPEN_AFTER_CREATE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "YETTEL_DEFAULT_FORMAT=xlsx\nYETTEL_EXPORT_OPEN_AFTER_CREATE=yes\n",
        encoding="utf-8",
    )

    config = AppConfig.from_values(env_file=env_file, project_root=tmp_path)

    assert config.default_format == "xlsx"
    assert config.export_open_after_create is True


def test_menu_can_exit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "10")

    assert main(["--env-file", str(tmp_path / ".env"), "--cookie-file", str(tmp_path / "cookies.txt")]) == 0


def test_menu_ctrl_c_exits_cleanly(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    def interrupt(_prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)

    assert main(["--env-file", str(tmp_path / ".env"), "--cookie-file", str(tmp_path / "cookies.txt")]) == 130
    assert "Exiting." in capsys.readouterr().out
