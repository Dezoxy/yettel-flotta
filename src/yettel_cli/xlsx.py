from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .models import UsageResult
from .report import BusinessReport, build_summaries


@dataclass(frozen=True)
class WorksheetSpec:
    name: str
    rows: list[list[object]]
    widths: list[float]
    freeze_header: bool = True
    autofilter: bool = True


def write_usage_xlsx(path: Path, results: list[UsageResult], report: BusinessReport | None = None) -> None:
    if report is None:
        report = BusinessReport(
            generated_at=datetime.now().astimezone(),
            results=results,
            summaries=build_summaries(results, []),
            warnings=[],
            changes=[],
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    sheets = build_sheets(report)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml(len(sheets)))
        workbook.writestr("_rels/.rels", root_rels_xml())
        workbook.writestr("docProps/core.xml", core_xml(report.generated_at))
        workbook.writestr("docProps/app.xml", app_xml())
        workbook.writestr("xl/workbook.xml", workbook_xml(sheets))
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml(sheets))
        workbook.writestr("xl/styles.xml", styles_xml())
        for index, sheet in enumerate(sheets, start=1):
            workbook.writestr(f"xl/worksheets/sheet{index}.xml", worksheet_xml(sheet))


def build_sheets(report: BusinessReport) -> list[WorksheetSpec]:
    summary_rows: list[list[object]] = [
        ["Yettel Usage Report"],
        ["Generated at", report.generated_at.isoformat(timespec="seconds")],
        ["Phone count", report.phone_count],
        ["Usage rows", report.row_count],
        ["Warnings", len(report.warnings)],
        ["Changes since last history snapshot", len(report.changes)],
        [],
        [
            "phone",
            "fetched_at",
            "data_item",
            "data_available",
            "data_limit",
            "sms_available",
            "valid_until",
            "warning_count",
        ],
    ]
    summary_rows.extend(
        [
            summary.phone,
            summary.fetched_at,
            summary.data_item,
            summary.data_available,
            summary.data_limit,
            summary.sms_available,
            summary.valid_until,
            summary.warning_count,
        ]
        for summary in report.summaries
    )

    usage_rows: list[list[object]] = [["phone", "fetched_at", "name", "limit", "available", "valid_until"]]
    for result in report.results:
        usage_rows.extend(
            [
                result.phone,
                result.fetched_at.isoformat(timespec="seconds"),
                row.name,
                row.limit,
                row.available,
                row.valid_until,
            ]
            for row in result.rows
        )

    warning_rows: list[list[object]] = [["severity", "phone", "item", "message", "available", "limit", "valid_until"]]
    warning_rows.extend(
        [
            warning.severity,
            warning.phone,
            warning.item,
            warning.message,
            warning.available,
            warning.limit,
            warning.valid_until,
        ]
        for warning in report.warnings
    )

    change_rows: list[list[object]] = [
        ["phone", "item", "previous_available", "current_available", "delta", "previous_fetched_at"]
    ]
    change_rows.extend(
        [
            change.phone,
            change.item,
            change.previous_available,
            change.current_available,
            change.delta,
            change.previous_fetched_at,
        ]
        for change in report.changes
    )

    return [
        WorksheetSpec("Summary", summary_rows, [16, 28, 34, 16, 16, 16, 14, 14]),
        WorksheetSpec("Usage", usage_rows, [16, 28, 44, 16, 16, 14]),
        WorksheetSpec("Warnings", warning_rows, [12, 16, 44, 36, 16, 16, 14]),
        WorksheetSpec("Changes", change_rows, [16, 44, 18, 18, 14, 28]),
    ]


def worksheet_xml(sheet: WorksheetSpec) -> str:
    max_cols = max((len(row) for row in sheet.rows), default=1)
    max_rows = max(len(sheet.rows), 1)
    dimension = f"A1:{column_name(max_cols)}{max_rows}"
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(sheet.widths, start=1)
    )
    rows = "\n".join(row_xml(row, row_index, sheet.name) for row_index, row in enumerate(sheet.rows, start=1))
    pane = (
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        if sheet.freeze_header
        else '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    )
    autofilter = f'<autoFilter ref="A8:{column_name(max_cols)}{max_rows}"/>' if sheet.name == "Summary" else ""
    if sheet.autofilter and sheet.name != "Summary":
        autofilter = f'<autoFilter ref="A1:{column_name(max_cols)}{max_rows}"/>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/>'
        f"{pane}"
        f"<cols>{cols}</cols>"
        f"<sheetData>{rows}</sheetData>"
        f"{autofilter}"
        "</worksheet>"
    )


def row_xml(row: list[object], row_index: int, sheet_name: str) -> str:
    style = style_for_row(row_index, sheet_name)
    cells = "".join(cell_xml(value, row_index, col_index, style) for col_index, value in enumerate(row, start=1))
    height = ' ht="24" customHeight="1"' if row_index == 1 else ""
    return f'<row r="{row_index}"{height}>{cells}</row>'


def cell_xml(value: object, row_index: int, col_index: int, style: int) -> str:
    reference = f"{column_name(col_index)}{row_index}"
    style_attr = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{reference}"{style_attr}/>'
    if isinstance(value, int | float):
        return f'<c r="{reference}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t>{escape(str(value))}</t></is></c>'


def style_for_row(row_index: int, sheet_name: str) -> int:
    if sheet_name == "Summary" and row_index == 1:
        return 1
    if (sheet_name == "Summary" and row_index == 8) or (sheet_name != "Summary" and row_index == 1):
        return 2
    return 0


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def content_types_xml(sheet_count: int) -> str:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{sheet_overrides}"
        "</Types>"
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def workbook_xml(sheets: list[WorksheetSpec]) -> str:
    sheet_nodes = "".join(
        f'<sheet name="{escape(sheet.name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, sheet in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_nodes}</sheets>"
        "</workbook>"
    )


def workbook_rels_xml(sheets: list[WorksheetSpec]) -> str:
    sheet_rels = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index, _sheet in enumerate(sheets, start=1)
    )
    style_id = len(sheets) + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{sheet_rels}"
        f'<Relationship Id="rId{style_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="11"/><name val="Aptos"/></font>'
        '<font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>'
        "</fonts>"
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0B5C4A"/><bgColor indexed="64"/></patternFill></fill>'
        "</fills>"
        '<borders count="2">'
        "<border><left/><right/><top/><bottom/><diagonal/></border>"
        '<border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/><diagonal/></border>'
        "</borders>"
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/>'
        '<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFill="1" applyFont="1" applyBorder="1"/>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def core_xml(created_at: datetime) -> str:
    timestamp = created_at.astimezone().isoformat(timespec="seconds")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>Yettel Usage Report</dc:title>"
        "<dc:creator>yettel-flotta</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>yettel-flotta</Application>"
        "</Properties>"
    )
