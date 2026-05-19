from __future__ import annotations

import csv
import json
import re
import sys
from io import StringIO
from pathlib import Path

from .models import UsageResult


def usage_result_dicts(result: UsageResult, *, include_phone: bool = False) -> list[dict[str, str]]:
    rows = []
    for row in result.rows:
        item = row.to_dict()
        if include_phone:
            item = {
                "phone": result.phone,
                "fetched_at": result.fetched_at.isoformat(timespec="seconds"),
                **item,
            }
        rows.append(item)
    return rows


def print_usage_result(result: UsageResult, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    if output_format == "csv":
        sys.stdout.write(render_usage_csv([result]))
        return

    print(f"Phone: {result.phone}")
    for row in result.rows:
        print(f"{row.name}: {row.available} / {row.limit} (valid until {row.valid_until})")


def print_usage_results(results: list[UsageResult], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
        return

    if output_format == "csv":
        sys.stdout.write(render_usage_csv(results))
        return

    for result in results:
        print_usage_result(result, "text")
        print()


def export_usage_result(result: UsageResult, export_dir: Path, output_format: str) -> Path:
    path = export_dir / export_name(f"usage_{safe_filename(result.phone)}", result.fetched_at, output_format)
    export_dir.mkdir(parents=True, exist_ok=True)
    write_export(path, render_single_result(result, output_format), output_format)
    return path


def export_usage_results(results: list[UsageResult], export_dir: Path, output_format: str) -> Path:
    fetched_at = results[0].fetched_at if results else None
    timestamp = fetched_at.strftime("%Y%m%d_%H%M%S") if fetched_at else "empty"
    path = export_dir / f"usage_all_{timestamp}.{extension_for(output_format)}"
    export_dir.mkdir(parents=True, exist_ok=True)
    write_export(path, render_many_results(results, output_format), output_format)
    return path


def render_single_result(result: UsageResult, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if output_format == "csv":
        return render_usage_csv([result])
    return render_usage_text([result])


def render_many_results(results: list[UsageResult], output_format: str) -> str:
    if output_format == "json":
        return json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2) + "\n"
    if output_format == "csv":
        return render_usage_csv(results)
    return render_usage_text(results)


def render_usage_text(results: list[UsageResult]) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(f"Phone: {result.phone}")
        for row in result.rows:
            lines.append(f"{row.name}: {row.available} / {row.limit} (valid until {row.valid_until})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_usage_csv(results: list[UsageResult]) -> str:
    output = StringIO()
    output.write("\ufeff")
    writer = csv.DictWriter(
        output,
        fieldnames=["phone", "fetched_at", "name", "limit", "available", "valid_until"],
        delimiter=";",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )
    writer.writeheader()
    for result in results:
        writer.writerows(usage_result_dicts(result, include_phone=True))
    return output.getvalue()


def write_export(path: Path, content: str, output_format: str) -> None:
    encoding = "utf-8-sig" if output_format == "csv" and not content.startswith("\ufeff") else "utf-8"
    path.write_text(content, encoding=encoding)


def export_name(prefix: str, fetched_at, output_format: str) -> str:
    return f"{prefix}_{fetched_at.strftime('%Y%m%d_%H%M%S')}.{extension_for(output_format)}"


def extension_for(output_format: str) -> str:
    return "txt" if output_format == "text" else output_format


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "unknown"
