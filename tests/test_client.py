from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from yettel_cli.client import YettelClient
from yettel_cli.config import AppConfig
from yettel_cli.constants import PHONE_POSTBACK, PHONE_SELECT
from yettel_cli.errors import PhoneNotFoundError, SessionExpiredError

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeHeaders:
    def get_content_charset(self) -> str:
        return "utf-8"


@dataclass
class FakeResponse:
    body: str
    url: str
    headers: FakeHeaders = FakeHeaders()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return self.body.encode("utf-8")


class FakeOpener:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests = []

    def open(self, request, timeout: int):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("No fake response queued")
        return self.responses.pop(0)


def config(tmp_path: Path) -> AppConfig:
    return AppConfig.from_values(
        env_file=tmp_path / ".env",
        cookie_file=tmp_path / "cookies.txt",
        export_dir=tmp_path / "exports",
        db_path=tmp_path / "history.sqlite3",
        project_root=tmp_path,
    )


def posted_form(fake_opener: FakeOpener, index: int) -> dict[str, list[str]]:
    data = fake_opener.requests[index].data.decode("utf-8")
    return parse_qs(data)


def test_login_posts_credentials_and_webforms_fields(tmp_path: Path) -> None:
    fake = FakeOpener(
        [
            FakeResponse(fixture("login.html"), "https://online.yettel.hu/ugyfelszolgalat/fwk/Login2.aspx"),
            FakeResponse(
                "<html><body>dashboard</body></html>", "https://online.yettel.hu/ugyfelszolgalat/pol/Usage.aspx"
            ),
        ]
    )
    client = YettelClient(config(tmp_path), opener=fake)

    client.login("user1", "pass1")

    form = posted_form(fake, 1)
    assert form["tbUserName"] == ["user1"]
    assert form["tbPassword"] == ["pass1"]
    assert form["__EVENTTARGET"] == ["bnLogin"]
    assert form["__VIEWSTATE"] == ["VIEWSTATE_VALUE"]


def test_usage_posts_selected_phone_and_event_target(tmp_path: Path) -> None:
    fake = FakeOpener(
        [
            FakeResponse(fixture("usage.html"), "https://online.yettel.hu/ugyfelszolgalat/pol/Usage.aspx"),
            FakeResponse(fixture("usage_result.html"), "https://online.yettel.hu/ugyfelszolgalat/pol/Usage.aspx"),
        ]
    )
    client = YettelClient(config(tmp_path), opener=fake)

    result = client.usage("20 123 4567")

    form = posted_form(fake, 1)
    assert form[PHONE_SELECT] == ["201234567"]
    assert form["__EVENTTARGET"] == [PHONE_POSTBACK]
    assert result.phone == "201234567"
    assert result.rows[0].available == "100 db"


def test_usage_rejects_phone_not_in_dropdown(tmp_path: Path) -> None:
    fake = FakeOpener(
        [
            FakeResponse(fixture("usage.html"), "https://online.yettel.hu/ugyfelszolgalat/pol/Usage.aspx"),
        ]
    )
    client = YettelClient(config(tmp_path), opener=fake)

    with pytest.raises(PhoneNotFoundError):
        client.usage("209000000")


def test_usage_page_detects_expired_session(tmp_path: Path) -> None:
    fake = FakeOpener(
        [
            FakeResponse(fixture("login.html"), "https://online.yettel.hu/ugyfelszolgalat/fwk/Login2.aspx"),
        ]
    )
    client = YettelClient(config(tmp_path), opener=fake)

    with pytest.raises(SessionExpiredError):
        client.usage_page()
