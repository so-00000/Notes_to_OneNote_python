from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.data_type_config import get_data_type_settings


_INVALID_XML_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
COMMON_MAPPING_PATH = REPO_ROOT / "main" / "resources" / "mapping" / "cmn_mapping.json"
COMMON_LOGICAL_NAMES = {
    "source_id": "ソースID",
    "replica_id": "レプリカID",
    "unid": "UNID",
    "form": "フォーム",
    "title": "タイトル",
    "doc_date": "基準日",
    "onenote_page_id": "OneNoteページID",
    "onenote_web_url": "OneNote（ブラウザ）",
    "onenote_client_url": "OneNote（アプリ）",
    "url_from_error": "エラーURL",
    "migration_status": "移行ステータス",
    "error_message": "エラーメッセージ",
    "processed_at": "処理日時",
    "link_resolution_status": "リンク解決状態",
}
VIEW_LOGICAL_NAME_FALLBACKS = {
    "documentdate": "日付",
    "documentno": "No.",
    "entryuser": "入力者",
    "status": "状況",
    "system": "分類2",
    "subsystem": "分類3",
    "fd_text_1": "件名",
    "worktime": "分数",
    "ask": "依頼部署",
    "askuser": "依頼担当者",
    "documentdate_2": "開始日",
    "replydate": "終了日",
    "detailsubject": "内容",
    "reasonsubject_1": "原因・理由",
}


def _default_csv_path() -> Path:
    settings = get_data_type_settings()
    return REPO_ROOT / "main" / "doc_mapping" / settings.view_name / "migration_master.csv"


def _sanitize_xml_text(value: object) -> str:
    text = "" if value is None else str(value)
    return _INVALID_XML_RE.sub("", text)


def _load_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    for encoding in ("utf-8", "utf-8-sig", "cp932"):
        try:
            with csv_path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                headers = list(reader.fieldnames or [])
                rows = list(reader)
                return headers, rows
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"unsupported encoding: {csv_path}")


def _load_common_headers() -> list[str]:
    if not COMMON_MAPPING_PATH.exists():
        return []
    data = json.loads(COMMON_MAPPING_PATH.read_text(encoding="utf-8"))
    return [
        str(col.get("key") or "").strip()
        for col in data.get("common_columns", [])
        if str(col.get("key") or "").strip()
    ]


def _load_mapping_view_columns(csv_path: Path) -> list[dict[str, str]]:
    mapping_path = REPO_ROOT / "main" / "resources" / "mapping" / csv_path.parent.name / "mapping.json"
    if not mapping_path.exists():
        return []

    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    view_columns: list[dict[str, str]] = []
    for view in data.get("views", {}).values():
        view_columns.extend(view.get("view_columns", []))
    return sorted(
        view_columns,
        key=lambda col: int(col.get("column_index") or 0),
    )


def _build_excel_columns(csv_headers: list[str], csv_path: Path) -> list[tuple[str, str]]:
    common_headers = _load_common_headers()
    common_set = set(common_headers)
    csv_header_set = set(csv_headers)

    columns: list[tuple[str, str]] = []
    for header in ("onenote_web_url", "onenote_client_url"):
        if header in csv_header_set:
            columns.append((header, COMMON_LOGICAL_NAMES.get(header, header)))

    mapped_output_keys: set[str] = set()
    for col in _load_mapping_view_columns(csv_path):
        output_key = str(col.get("output_key") or "").strip()
        if not output_key or output_key in common_set or output_key == "view_name":
            continue
        logical_name = str(col.get("logical_name") or "").strip()
        item_name = str(col.get("item_name") or "").strip()
        columns.append(
            (
                output_key,
                logical_name
                or VIEW_LOGICAL_NAME_FALLBACKS.get(output_key, "")
                or item_name
                or output_key,
            )
        )
        mapped_output_keys.add(output_key)

    for header in csv_headers:
        if header in common_set or header == "view_name":
            continue
        if header in {"onenote_web_url", "onenote_client_url"}:
            continue
        if header in mapped_output_keys:
            continue
        columns.append(
            (
                header,
                COMMON_LOGICAL_NAMES.get(header)
                or VIEW_LOGICAL_NAME_FALLBACKS.get(header)
                or header,
            )
        )

    return columns


def _column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, rem = divmod(current - 1, 26)
        name = chr(65 + rem) + name
    return name


def _cell_ref(row_index: int, col_index: int) -> str:
    return f"{_column_name(col_index)}{row_index}"


def _inline_string_cell(row_index: int, col_index: int, value: object) -> str:
    safe = escape(_sanitize_xml_text(value))
    return (
        f'<c r="{_cell_ref(row_index, col_index)}" t="inlineStr">'
        f"<is><t xml:space=\"preserve\">{safe}</t></is>"
        f"</c>"
    )


def _styled_inline_string_cell(row_index: int, col_index: int, value: object, style_index: int) -> str:
    safe = escape(_sanitize_xml_text(value))
    return (
        f'<c r="{_cell_ref(row_index, col_index)}" s="{style_index}" t="inlineStr">'
        f"<is><t xml:space=\"preserve\">{safe}</t></is>"
        f"</c>"
    )


def _hyperlink_label(header: str) -> str | None:
    if header == "onenote_web_url":
        return "OneNote（ブラウザ）"
    if header == "onenote_client_url":
        return "OneNote（アプリ）"
    return None


def _build_sheet_xml(
    columns: list[tuple[str, str]],
    rows: list[dict[str, str]],
) -> tuple[str, str | None]:
    sheet_rows: list[str] = []
    hyperlink_rows: list[str] = []
    hyperlink_rels: list[str] = []
    hyperlink_id = 1

    logical_header_cells = [
        _inline_string_cell(1, col_index, logical_header)
        for col_index, (_, logical_header) in enumerate(columns, start=1)
    ]
    sheet_rows.append(f'<row r="1">{"".join(logical_header_cells)}</row>')

    for row_index, row in enumerate(rows, start=2):
        cells: list[str] = []
        for col_index, (source_key, _) in enumerate(columns, start=1):
            value = row.get(source_key, "")
            link_label = _hyperlink_label(source_key)
            if link_label and value:
                cell_ref = _cell_ref(row_index, col_index)
                cells.append(_styled_inline_string_cell(row_index, col_index, link_label, 1))
                hyperlink_rows.append(f'<hyperlink ref="{cell_ref}" r:id="rId{hyperlink_id}"/>')
                hyperlink_rels.append(
                    "<Relationship "
                    f'Id="rId{hyperlink_id}" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                    f'Target="{escape(_sanitize_xml_text(value))}" TargetMode="External"/>'
                )
                hyperlink_id += 1
            else:
                cells.append(_inline_string_cell(row_index, col_index, value))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    last_col = _column_name(max(len(columns), 1))
    last_row = max(len(rows) + 1, 1)
    dimension = f"A1:{last_col}{last_row}"
    hyperlinks_xml = f"<hyperlinks>{''.join(hyperlink_rows)}</hyperlinks>" if hyperlink_rows else ""

    # Inline strings keep the workbook dependency-free while preserving all CSV values as text.
    sheet_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        f"<dimension ref=\"{dimension}\"/>"
        "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        "<sheetData>"
        f"{''.join(sheet_rows)}"
        "</sheetData>"
        f"{hyperlinks_xml}"
        "</worksheet>"
    )
    sheet_rels_xml = None
    if hyperlink_rels:
        sheet_rels_xml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            f"{''.join(hyperlink_rels)}"
            "</Relationships>"
        )
    return sheet_xml, sheet_rels_xml


def _write_xlsx(output_path: Path, columns: list[tuple[str, str]], rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_xml, sheet_rels_xml = _build_sheet_xml(columns, rows)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/xl/workbook.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
            "<Override PartName=\"/xl/worksheets/sheet1.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
            "<Override PartName=\"/xl/styles.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>"
            "<Override PartName=\"/docProps/core.xml\" "
            "ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>"
            "<Override PartName=\"/docProps/app.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" "
            "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
            "Target=\"xl/workbook.xml\"/>"
            "<Relationship Id=\"rId2\" "
            "Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" "
            "Target=\"docProps/core.xml\"/>"
            "<Relationship Id=\"rId3\" "
            "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" "
            "Target=\"docProps/app.xml\"/>"
            "</Relationships>",
        )
        zf.writestr(
            "docProps/app.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" "
            "xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
            "<Application>Python</Application>"
            "</Properties>",
        )
        zf.writestr(
            "docProps/core.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" "
            "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" "
            "xmlns:dcterms=\"http://purl.org/dc/terms/\" "
            "xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" "
            "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
            "<dc:creator>Codex</dc:creator>"
            "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
            "</cp:coreProperties>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" "
            "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" "
            "Target=\"worksheets/sheet1.xml\"/>"
            "<Relationship Id=\"rId2\" "
            "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" "
            "Target=\"styles.xml\"/>"
            "</Relationships>",
        )
        zf.writestr(
            "xl/styles.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
            "<fonts count=\"2\">"
            "<font><sz val=\"11\"/><color theme=\"1\"/><name val=\"Calibri\"/><family val=\"2\"/></font>"
            "<font><u/><sz val=\"11\"/><color rgb=\"FF0563C1\"/><name val=\"Calibri\"/><family val=\"2\"/></font>"
            "</fonts>"
            "<fills count=\"2\">"
            "<fill><patternFill patternType=\"none\"/></fill>"
            "<fill><patternFill patternType=\"gray125\"/></fill>"
            "</fills>"
            "<borders count=\"1\">"
            "<border><left/><right/><top/><bottom/><diagonal/></border>"
            "</borders>"
            "<cellStyleXfs count=\"1\">"
            "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/>"
            "</cellStyleXfs>"
            "<cellXfs count=\"2\">"
            "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>"
            "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyFont=\"1\"/>"
            "</cellXfs>"
            "<cellStyles count=\"1\">"
            "<cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/>"
            "</cellStyles>"
            "</styleSheet>",
        )
        zf.writestr(
            "xl/workbook.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
            "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
            "<sheets>"
            "<sheet name=\"migration_master\" sheetId=\"1\" r:id=\"rId1\"/>"
            "</sheets>"
            "</workbook>",
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        if sheet_rels_xml is not None:
            zf.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_rels_xml)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export migration_master.csv to a single-sheet Excel file with all columns."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=str(_default_csv_path()),
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output .xlsx path. Default: next to the CSV with the same stem.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else csv_path.with_suffix(".xlsx")
    )

    headers, rows = _load_csv_rows(csv_path)
    if not headers:
        raise ValueError(f"CSV header not found: {csv_path}")
    columns = _build_excel_columns(headers, csv_path)

    _write_xlsx(output_path, columns, rows)
    print(
        f"[DONE] csv={csv_path} xlsx={output_path} headers={len(columns)} rows={len(rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
