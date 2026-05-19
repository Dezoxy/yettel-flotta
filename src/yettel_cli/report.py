from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from .config import AppConfig
from .models import UsageResult, UsageRow


@dataclass(frozen=True)
class ReportWarning:
    severity: str
    phone: str
    item: str
    message: str
    available: str
    limit: str
    valid_until: str


@dataclass(frozen=True)
class ChangeRow:
    phone: str
    item: str
    previous_available: str
    current_available: str
    delta: str
    previous_fetched_at: str


@dataclass(frozen=True)
class PhoneSummary:
    phone: str
    fetched_at: str
    data_item: str
    data_available: str
    data_limit: str
    sms_available: str
    valid_until: str
    warning_count: int


@dataclass(frozen=True)
class BusinessReport:
    generated_at: datetime
    results: list[UsageResult]
    summaries: list[PhoneSummary]
    warnings: list[ReportWarning]
    changes: list[ChangeRow]

    @property
    def phone_count(self) -> int:
        return len(self.results)

    @property
    def row_count(self) -> int:
        return sum(len(result.rows) for result in self.results)


def build_business_report(
    results: list[UsageResult],
    previous_results: dict[str, UsageResult],
    config: AppConfig,
) -> BusinessReport:
    warnings = build_warnings(results, config)
    changes = build_changes(results, previous_results)
    summaries = build_summaries(results, warnings)
    return BusinessReport(
        generated_at=datetime.now().astimezone(),
        results=results,
        summaries=summaries,
        warnings=warnings,
        changes=changes,
    )


def build_warnings(results: list[UsageResult], config: AppConfig) -> list[ReportWarning]:
    warnings: list[ReportWarning] = []
    today = date.today()

    for result in results:
        for row in result.rows:
            available_gb = parse_gb(row.available)
            if available_gb is not None and available_gb <= config.low_data_gb_threshold:
                warnings.append(
                    ReportWarning(
                        severity="warning",
                        phone=result.phone,
                        item=row.name,
                        message=f"Low data remaining: {available_gb:g} GB",
                        available=row.available,
                        limit=row.limit,
                        valid_until=row.valid_until,
                    )
                )

            valid_until = parse_yettel_date(row.valid_until)
            if valid_until is not None:
                days_left = (valid_until - today).days
                if days_left < 0:
                    message = f"Expired {abs(days_left)} day(s) ago"
                    severity = "critical"
                elif days_left <= config.expiry_warning_days:
                    message = f"Expires in {days_left} day(s)"
                    severity = "warning"
                else:
                    continue
                warnings.append(
                    ReportWarning(
                        severity=severity,
                        phone=result.phone,
                        item=row.name,
                        message=message,
                        available=row.available,
                        limit=row.limit,
                        valid_until=row.valid_until,
                    )
                )
    return warnings


def build_changes(results: list[UsageResult], previous_results: dict[str, UsageResult]) -> list[ChangeRow]:
    changes: list[ChangeRow] = []

    for result in results:
        previous = previous_results.get(result.phone)
        if previous is None:
            continue
        previous_by_name = {row.name: row for row in previous.rows}
        for row in result.rows:
            previous_row = previous_by_name.get(row.name)
            if previous_row is None or previous_row.available == row.available:
                continue
            changes.append(
                ChangeRow(
                    phone=result.phone,
                    item=row.name,
                    previous_available=previous_row.available,
                    current_available=row.available,
                    delta=format_delta(previous_row.available, row.available),
                    previous_fetched_at=previous.fetched_at.isoformat(timespec="seconds"),
                )
            )
    return changes


def build_summaries(results: list[UsageResult], warnings: list[ReportWarning]) -> list[PhoneSummary]:
    warnings_by_phone: dict[str, int] = {}
    for warning in warnings:
        warnings_by_phone[warning.phone] = warnings_by_phone.get(warning.phone, 0) + 1

    summaries: list[PhoneSummary] = []
    for result in results:
        data_row = preferred_data_row(result.rows)
        sms_row = preferred_sms_row(result.rows)
        summaries.append(
            PhoneSummary(
                phone=result.phone,
                fetched_at=result.fetched_at.isoformat(timespec="seconds"),
                data_item=data_row.name if data_row else "",
                data_available=data_row.available if data_row else "",
                data_limit=data_row.limit if data_row else "",
                sms_available=sms_row.available if sms_row else "",
                valid_until=(data_row.valid_until if data_row else first_valid_until(result.rows)),
                warning_count=warnings_by_phone.get(result.phone, 0),
            )
        )
    return summaries


def preferred_data_row(rows: list[UsageRow]) -> UsageRow | None:
    candidates = [
        row
        for row in rows
        if "adat" in row.name.lower() or parse_gb(row.available) is not None or parse_gb(row.limit) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: parse_gb(row.available) if parse_gb(row.available) is not None else -1)


def preferred_sms_row(rows: list[UsageRow]) -> UsageRow | None:
    return next((row for row in rows if "sms" in row.name.lower()), None)


def first_valid_until(rows: list[UsageRow]) -> str:
    return next((row.valid_until for row in rows if row.valid_until), "")


def parse_gb(value: str) -> float | None:
    text = value.strip().replace(",", ".")
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(gb|mb)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    return number / 1024 if unit == "mb" else number


def parse_quantity(value: str) -> tuple[float, str] | None:
    text = value.strip().replace(",", ".")
    if text.lower() in {"korlátlan", "korlatlan", "unlimited"}:
        return None
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([^\d\s]+)", text)
    if not match:
        return None
    return float(match.group(1)), match.group(2).lower()


def format_delta(previous: str, current: str) -> str:
    previous_quantity = parse_quantity(previous)
    current_quantity = parse_quantity(current)
    if previous_quantity is None or current_quantity is None:
        return ""
    previous_value, previous_unit = previous_quantity
    current_value, current_unit = current_quantity
    if previous_unit != current_unit:
        return ""
    delta = current_value - previous_value
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:g} {display_unit(current_unit)}"


def display_unit(unit: str) -> str:
    return unit.upper() if unit in {"gb", "mb"} else unit


def parse_yettel_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y.%m.%d").date()
    except ValueError:
        return None
