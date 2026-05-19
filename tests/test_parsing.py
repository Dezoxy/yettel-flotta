from __future__ import annotations

from pathlib import Path

import pytest

from yettel_cli.constants import PHONE_SELECT
from yettel_cli.errors import PortalLayoutError
from yettel_cli.parsing import first_form, normalize_phone, parse_phone_options, parse_usage_rows, redact_sensitive_html

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_form_parser_keeps_hidden_fields_and_select_options() -> None:
    form = first_form(fixture("usage.html"))

    assert form.fields["__VIEWSTATE"] == "USAGE_VIEWSTATE"
    assert form.fields[PHONE_SELECT] == "201234567"
    assert form.selects[PHONE_SELECT] == ["201111111", "201234567", "309999999"]


def test_parse_phone_options() -> None:
    phones = parse_phone_options(fixture("usage.html"))

    assert [phone.number for phone in phones] == ["201111111", "201234567", "309999999"]


def test_parse_usage_rows() -> None:
    rows = parse_usage_rows(fixture("usage_result.html"))

    assert rows[0].to_dict() == {
        "name": "SMS belföldön és 1. roaming díjzónában",
        "limit": "100 db",
        "available": "100 db",
        "valid_until": "2026.06.06",
    }
    assert rows[1].name == "EU roaming adatkeret"


def test_parse_usage_rows_errors_when_layout_changes() -> None:
    with pytest.raises(PortalLayoutError):
        parse_usage_rows("<html><body>No expected table</body></html>")


def test_normalize_phone() -> None:
    assert normalize_phone("+36 20 123 4567") == "36201234567"


def test_redact_sensitive_html() -> None:
    redacted = redact_sensitive_html('<input name="__VIEWSTATE" value="secret"><span>201234567</span>')

    assert "secret" not in redacted
    assert "201234567" not in redacted
