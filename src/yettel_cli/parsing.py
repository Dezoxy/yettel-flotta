from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

from .constants import PHONE_SELECT
from .errors import PortalLayoutError
from .models import PhoneNumber, UsageRow


@dataclass
class FormSnapshot:
    action: str | None = None
    method: str = "get"
    fields: dict[str, str] = field(default_factory=dict)
    selects: dict[str, list[str]] = field(default_factory=dict)


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[FormSnapshot] = []
        self._form: FormSnapshot | None = None
        self._select_name: str | None = None
        self._select_options: list[tuple[str, bool]] = []
        self._option_value: str | None = None
        self._option_selected = False
        self._option_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()

        if tag == "form":
            self._form = FormSnapshot(
                action=attr.get("action"),
                method=(attr.get("method") or "get").lower(),
            )
            return

        if self._form is None:
            return

        if tag == "input":
            name = attr.get("name")
            if not name or "disabled" in attr:
                return
            input_type = (attr.get("type") or "text").lower()
            if input_type in {"submit", "button", "image", "file", "reset"}:
                return
            if input_type in {"checkbox", "radio"} and "checked" not in attr:
                return
            self._form.fields[name] = attr.get("value", "")
            return

        if tag == "textarea":
            name = attr.get("name")
            if name and "disabled" not in attr:
                self._form.fields.setdefault(name, "")
            return

        if tag == "select":
            name = attr.get("name")
            if name and "disabled" not in attr:
                self._select_name = name
                self._select_options = []
            return

        if tag == "option" and self._select_name:
            self._option_value = attr.get("value")
            self._option_selected = "selected" in attr
            self._option_text = []

    def handle_data(self, data: str) -> None:
        if self._select_name and self._option_value is not None:
            self._option_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "option" and self._select_name and self._option_value is not None:
            text_value = clean_text("".join(self._option_text))
            value = self._option_value if self._option_value != "" else text_value
            self._select_options.append((value, self._option_selected))
            self._option_value = None
            self._option_selected = False
            self._option_text = []
            return

        if tag == "select" and self._form and self._select_name:
            values = [value for value, _selected in self._select_options]
            self._form.selects[self._select_name] = values
            selected = next((value for value, selected in self._select_options if selected), None)
            if selected is None and values:
                selected = values[0]
            if selected is not None:
                self._form.fields[self._select_name] = selected
            self._select_name = None
            self._select_options = []
            return

        if tag == "form" and self._form:
            self.forms.append(self._form)
            self._form = None


@dataclass
class ParsedTable:
    rows: list[list[str]] = field(default_factory=list)


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[ParsedTable] = []
        self._table_stack: list[ParsedTable] = []
        self._row_stack: list[list[str] | None] = []
        self._cell_stack: list[list[str] | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table_stack.append(ParsedTable())
            return
        if not self._table_stack:
            return
        if tag == "tr":
            self._row_stack.append([])
            return
        if tag in {"td", "th"} and self._row_stack:
            self._cell_stack.append([])

    def handle_data(self, data: str) -> None:
        if self._cell_stack:
            self._cell_stack[-1].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell_stack and self._row_stack:
            text = clean_text("".join(self._cell_stack.pop() or []))
            self._row_stack[-1].append(text)
            return
        if tag == "tr" and self._row_stack and self._table_stack:
            row = self._row_stack.pop() or []
            if any(cell for cell in row):
                self._table_stack[-1].rows.append(row)
            return
        if tag == "table" and self._table_stack:
            table = self._table_stack.pop()
            self.tables.append(table)


class AllowanceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[UsageRow] = []
        self._inside_allowances = False
        self._allowance_depth = 0
        self._current_row: dict[str, str] | None = None
        self._current_field: str | None = None
        self._field_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()

        if tag == "ul" and (attr.get("id") == "Allowances" or "SocTraffic" in attr.get("class", "")):
            self._inside_allowances = True
            self._allowance_depth = 1
            return

        if not self._inside_allowances:
            return

        self._allowance_depth += 1
        class_names = set(attr.get("class", "").split())

        if tag == "li" and "Row" in class_names:
            self._current_row = {}
            return

        if tag == "div" and self._current_row is not None:
            for field in ("Name", "Maximum", "Remaining", "EndDate"):
                if field in class_names:
                    self._current_field = field
                    self._field_parts = []
                    return

    def handle_data(self, data: str) -> None:
        if self._inside_allowances and self._current_field:
            self._field_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self._inside_allowances:
            return

        if tag == "div" and self._current_field and self._current_row is not None:
            self._current_row[self._current_field] = clean_text("".join(self._field_parts))
            self._current_field = None
            self._field_parts = []
            self._allowance_depth -= 1
            return

        if tag == "li" and self._current_row is not None:
            row = self._current_row
            if row.get("Name"):
                self.rows.append(
                    UsageRow(
                        name=row.get("Name", ""),
                        limit=row.get("Maximum", ""),
                        available=row.get("Remaining", ""),
                        valid_until=row.get("EndDate", ""),
                    )
                )
            self._current_row = None

        self._allowance_depth -= 1
        if tag == "ul" and self._allowance_depth <= 0:
            self._inside_allowances = False
            self._allowance_depth = 0


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def first_form(html: str) -> FormSnapshot:
    parser = FormParser()
    parser.feed(html)
    if not parser.forms:
        raise PortalLayoutError("No HTML form found in portal response.")
    return parser.forms[0]


def form_action_url(current_url: str, form: FormSnapshot) -> str:
    if not form.action:
        return current_url
    return urljoin(current_url, form.action)


def is_login_page(html: str, url: str = "") -> bool:
    return "tbUserName" in html or "Login2.aspx" in url


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D+", "", phone)


def parse_phone_options(html: str) -> list[PhoneNumber]:
    form = first_form(html)
    return [PhoneNumber(number=option) for option in form.selects.get(PHONE_SELECT, [])]


def parse_usage_rows(html: str) -> list[UsageRow]:
    allowance_parser = AllowanceParser()
    allowance_parser.feed(html)
    if allowance_parser.rows:
        return allowance_parser.rows

    parser = TableParser()
    parser.feed(html)

    for table in parser.tables:
        for index, row in enumerate(table.rows):
            normalized = [clean_text(cell).lower() for cell in row]
            if all(label in normalized for label in ["megnevezés", "keret", "felhasználható", "érvényesség vége"]):
                rows: list[UsageRow] = []
                for data_row in table.rows[index + 1 :]:
                    if len(data_row) < 4:
                        continue
                    name, limit, available, valid_until = data_row[:4]
                    if not name or name.startswith("*"):
                        continue
                    rows.append(
                        UsageRow(
                            name=name,
                            limit=limit,
                            available=available,
                            valid_until=valid_until,
                        )
                    )
                if rows:
                    return rows

    raise PortalLayoutError("Could not find the 'Forgalmi adatok' table in the portal response.")


def extract_login_error(html: str) -> str | None:
    text = clean_text(re.sub(r"<[^>]+>", " ", html))
    known = [
        "Felhasználónév",
        "Jelszó",
        "Belépés",
        "hibás",
        "sikertelen",
        "nem megfelelő",
    ]
    if any(word.lower() in text.lower() for word in known):
        return "Login failed. Check YETTEL_USERNAME and YETTEL_PASSWORD in .env."
    return None


def redact_sensitive_html(html: str) -> str:
    redacted = re.sub(
        r'(<input[^>]+name=["\']__(?:VIEWSTATE|EVENTVALIDATION)["\'][^>]+value=["\'])([^"\']+)(["\'])',
        r"\1[REDACTED]\3",
        html,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(r"\b(?:20|30|31|50|70)\d{7}\b", "[PHONE]", redacted)
    redacted = re.sub(r"\b\d{8,12}\b", "[NUMBER]", redacted)
    return redacted
