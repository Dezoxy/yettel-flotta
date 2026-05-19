from __future__ import annotations

import stat
from datetime import datetime
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .config import AppConfig
from .constants import BASE_URL, LOGIN_PATH, PHONE_POSTBACK, PHONE_SELECT, PHONE_TEXT, USAGE_PATH
from .errors import AuthenticationError, PhoneNotFoundError, PortalLayoutError, PortalRequestError, SessionExpiredError
from .models import PhoneNumber, UsageResult
from .parsing import (
    extract_login_error,
    first_form,
    form_action_url,
    form_with_select,
    is_login_page,
    normalize_phone,
    parse_phone_options,
    parse_usage_rows,
    redact_sensitive_html,
)


class YettelClient:
    def __init__(self, config: AppConfig, opener: object | None = None) -> None:
        self.config = config
        self.cookie_file = config.cookie_file
        self.cookies = MozillaCookieJar(str(self.cookie_file))
        if self.cookie_file.exists():
            self.cookies.load(ignore_discard=True, ignore_expires=True)
        self.opener = opener or build_opener(HTTPCookieProcessor(self.cookies))
        self.last_url = ""

    def cookie_file_exists(self) -> bool:
        return self.cookie_file.exists() and self.cookie_file.stat().st_size > 0

    def session_status_label(self) -> str:
        return "cookie saved" if self.cookie_file_exists() else "no saved session"

    def save_cookies(self) -> None:
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookies.save(ignore_discard=True, ignore_expires=True)
        self.cookie_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def request(self, url: str, data: dict[str, str] | None = None) -> str:
        encoded = None if data is None else urlencode(data).encode("utf-8")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 YettelCli/0.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.7",
            "Origin": BASE_URL,
            "Referer": url,
        }
        request = Request(url, data=encoded, headers=headers)

        for attempt in range(self.config.retries + 1):
            try:
                with self.opener.open(request, timeout=self.config.timeout_seconds) as response:
                    self.last_url = response.geturl()
                    charset_getter = getattr(response.headers, "get_content_charset", None)
                    charset = charset_getter() if charset_getter else None
                    body = response.read().decode(charset or "utf-8", errors="replace")
                self.save_cookies()
                return body
            except HTTPError as error:
                if error.code >= 500 and attempt < self.config.retries:
                    continue
                raise PortalRequestError(f"HTTP {error.code} from Yettel portal.") from error
            except URLError as error:
                if attempt < self.config.retries:
                    continue
                raise PortalRequestError(f"Could not reach Yettel portal: {error.reason}") from error

        raise PortalRequestError("Could not reach Yettel portal.")

    def login(self, username: str, password: str) -> None:
        login_url = urljoin(BASE_URL, LOGIN_PATH)
        html = self.request(login_url)
        form = first_form(html)
        fields = dict(form.fields)
        fields.update(
            {
                "tbUserName": username,
                "tbPassword": password,
                "__EVENTTARGET": "bnLogin",
                "__EVENTARGUMENT": "",
            }
        )
        html = self.request(form_action_url(login_url, form), fields)
        if is_login_page(html, self.last_url):
            message = extract_login_error(html)
            raise AuthenticationError(message or "Login did not reach the authenticated portal.")

    def usage_page(self) -> str:
        html = self.request(urljoin(BASE_URL, USAGE_PATH))
        if is_login_page(html, self.last_url):
            raise SessionExpiredError("Session expired or not logged in. Run `yettel login` first.")
        return html

    def session_alive(self) -> bool:
        try:
            self.usage_page()
        except SessionExpiredError:
            return False
        return True

    def phones(self) -> list[PhoneNumber]:
        html = self.usage_page()
        phones = parse_phone_options(html)
        if phones:
            return phones
        debug_path = self._write_debug_html(html, "phones-empty")
        if debug_path:
            raise PortalLayoutError(
                f"Could not find phone numbers in the portal response. Redacted debug HTML saved to {debug_path}."
            )
        raise PortalLayoutError(
            "Could not find phone numbers in the portal response. "
            "Run `yettel status --check-remote`; if the session is active, set YETTEL_DEBUG_HTML_DIR and retry."
        )

    def usage(self, phone: str) -> UsageResult:
        html = self.usage_page()
        form = form_with_select(html, PHONE_SELECT)
        fields = dict(form.fields)
        options = form.selects.get(PHONE_SELECT, [])
        normalized_phone = normalize_phone(phone)

        matching_option = next((option for option in options if normalize_phone(option) == normalized_phone), None)
        if matching_option is None and options:
            raise PhoneNotFoundError(f"Phone number {phone} is not present in the portal dropdown.")

        fields[PHONE_SELECT] = matching_option or phone
        fields[PHONE_TEXT] = ""
        fields["__EVENTTARGET"] = PHONE_POSTBACK
        fields["__EVENTARGUMENT"] = ""

        html = self.request(form_action_url(urljoin(BASE_URL, USAGE_PATH), form), fields)
        if is_login_page(html, self.last_url):
            raise SessionExpiredError("Session expired while requesting usage data. Run `yettel login` first.")

        try:
            rows = parse_usage_rows(html)
        except PortalLayoutError as error:
            debug_path = self._write_debug_html(html, f"usage-layout-error-{matching_option or phone}")
            if debug_path:
                raise PortalLayoutError(f"{error} Redacted debug HTML saved to {debug_path}.") from error
            raise PortalLayoutError(f"{error} Set YETTEL_DEBUG_HTML_DIR to save redacted debug HTML.") from error

        return UsageResult(phone=matching_option or phone, rows=rows, fetched_at=datetime.now().astimezone())

    def all_usage(self) -> list[UsageResult]:
        return [self.usage(phone.number) for phone in self.phones()]

    def _write_debug_html(self, html: str, label: str) -> Path | None:
        if not self.config.debug_html_dir:
            return None
        self.config.debug_html_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.debug_html_dir / f"{label}.html"
        path.write_text(redact_sensitive_html(html), encoding="utf-8")
        return path
