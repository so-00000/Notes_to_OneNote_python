from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.services.dxl_to_ui_field_map import dxl_to_field_map


DXL_NS = {"dxl": "http://www.lotus.com/dxl"}
CSV_LINEBREAK_RE = re.compile(r"[\r\n]+")
VIEW_NAME = "VwData_Patch_1_3ALL"

COMMON_MAPPING_PATH = REPO_ROOT / "main" / "resources" / "mapping" / "cmn_mapping.json"
VIEW_MAPPING_PATH = REPO_ROOT / "main" / "resources" / "mapping" / VIEW_NAME / "mapping.json"
OLD_CSV_PATH = REPO_ROOT / "main" / "doc_mapping" / VIEW_NAME / "OLD_migration_master.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "main" / "doc_mapping" / VIEW_NAME / "migration_master_rebuilt.csv"
DXL_ROOT = REPO_ROOT / "main" / "1_target_dxl" / "Fm_Document_3" / "result"

DXL_PRIORITY_DIR_ORDER = (
    "complete_データ強制変更_2018",
    "complete_データ強制変更_2019",
    "complete_データ強制変更_2020",
    "complete_データ強制変更_2021",
    "complete_データ強制変更_2022",
    "complete_データ強制変更_2023",
    "complete_データ強制変更_2024",
    "complete_BK",
    "duplicate",
    "error",
)

OLD_PRIORITY_COLUMNS = {
    "source_id",
    "replica_id",
    "unid",
    "onenote_page_id",
    "onenote_web_url",
    "onenote_client_url",
    "url_from_error",
    "migration_status",
    "error_message",
    "processed_at",
    "link_resolution_status",
}

DXL_PRIORITY_COLUMNS = {
    "form": "Form",
    "title": "Fd_Text_1",
    "doc_date": "DocumentDate",
    "documentdate": "DocumentDate",
    "documentno": "DocumentNo",
    "entryuser": "EntryUser",
    "status": "Status",
    "system": "System",
    "subsystem": "SubSystem",
    "fd_text_1": "Fd_Text_1",
    "worktime": "WorkTime",
    "ask": "Ask",
    "askuser": "AskUser",
    "documentdate_2": "DocumentDate",
    "replydate": "ReplyDate",
    "detailsubject": "DetailSubject",
    "reasonsubject_1": "ReasonSubject_1",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_headers(common_mapping: dict, view_mapping: dict) -> list[str]:
    headers = ["view_name"]
    seen = {"view_name"}

    for col in common_mapping.get("common_columns", []):
        key = str(col.get("key") or "").strip()
        if key and key not in seen:
            headers.append(key)
            seen.add(key)

    for view in view_mapping.get("views", {}).values():
        for col in view.get("view_columns", []):
            key = str(col.get("output_key") or "").strip()
            if key and key not in seen:
                headers.append(key)
                seen.add(key)

    return headers


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"unable to decode: {csv_path}")


def _normalize_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return CSV_LINEBREAK_RE.sub(" ", text).strip()


def _write_csv(csv_path: Path, headers: list[str], rows: Iterable[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(
            [
                {header: _normalize_csv_cell(row.get(header, "")) for header in headers}
                for row in rows
            ]
        )


def _mapping_item_names(view_mapping: dict) -> set[str]:
    item_names = {"Form"}
    for view in view_mapping.get("views", {}).values():
        for col in view.get("view_columns", []):
            item_name = str(col.get("item_name") or "").strip()
            if item_name:
                item_names.add(item_name)
    return item_names


def _preferred_dxl_dir_index(path: Path) -> int:
    path_text = str(path)
    for i, name in enumerate(DXL_PRIORITY_DIR_ORDER):
        if name in path_text:
            return i
    return len(DXL_PRIORITY_DIR_ORDER)


def _build_unid_to_dxl_map(dxl_root: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for path in dxl_root.rglob("*.dxl"):
        stem = path.stem
        if "_" not in stem:
            continue
        _, unid = stem.split("_", 1)
        current = mapping.get(unid)
        if current is None:
            mapping[unid] = path
            continue
        if (_preferred_dxl_dir_index(path), str(path)) < (
            _preferred_dxl_dir_index(current),
            str(current),
        ):
            mapping[unid] = path
    return mapping


def _extract_dxl_fields(dxl_path: Path, target_field_names: set[str]) -> dict[str, str]:
    root = ET.parse(dxl_path).getroot()
    return dxl_to_field_map(root, target_field_names=target_field_names)


def _merge_row(
    *,
    old_row: dict[str, str],
    headers: list[str],
    dxl_fields: dict[str, str] | None,
) -> dict[str, str]:
    merged = {header: old_row.get(header, "") for header in headers}
    merged["view_name"] = old_row.get("view_name") or VIEW_NAME

    if not dxl_fields:
        return merged

    for column, item_name in DXL_PRIORITY_COLUMNS.items():
        if column not in merged:
            continue
        value = dxl_fields.get(item_name, "")
        if value:
            merged[column] = value

    for column in OLD_PRIORITY_COLUMNS:
        if column in headers:
            merged[column] = old_row.get(column, "")

    return merged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild VwData_Patch_1_3ALL migration master from OLD CSV and DXL."
    )
    parser.add_argument(
        "--old-csv",
        type=Path,
        default=OLD_CSV_PATH,
        help=f"default: {OLD_CSV_PATH}",
    )
    parser.add_argument(
        "--dxl-root",
        type=Path,
        default=DXL_ROOT,
        help=f"default: {DXL_ROOT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"default: {DEFAULT_OUTPUT_PATH}",
    )
    args = parser.parse_args()

    common_mapping = _load_json(COMMON_MAPPING_PATH)
    view_mapping = _load_json(VIEW_MAPPING_PATH)
    headers = _build_headers(common_mapping, view_mapping)
    target_field_names = _mapping_item_names(view_mapping)

    old_rows = _read_csv_rows(args.old_csv)
    unid_to_dxl = _build_unid_to_dxl_map(args.dxl_root)

    dxl_cache: dict[str, dict[str, str]] = {}
    rebuilt_rows: list[dict[str, str]] = []
    matched = 0
    unmatched = 0
    parse_errors = 0

    for old_row in old_rows:
        unid = old_row.get("unid", "")
        dxl_path = unid_to_dxl.get(unid)
        dxl_fields: dict[str, str] | None = None

        if dxl_path is None:
            unmatched += 1
        else:
            if unid not in dxl_cache:
                try:
                    dxl_cache[unid] = _extract_dxl_fields(dxl_path, target_field_names)
                except ET.ParseError:
                    parse_errors += 1
                    dxl_cache[unid] = {}
            dxl_fields = dxl_cache[unid]
            if dxl_fields:
                matched += 1
            else:
                unmatched += 1

        rebuilt_rows.append(_merge_row(old_row=old_row, headers=headers, dxl_fields=dxl_fields))

    _write_csv(args.output, headers, rebuilt_rows)

    print(f"[DONE] output={args.output}")
    print(f"rows={len(rebuilt_rows)} headers={len(headers)}")
    print(f"dxl_candidates={len(unid_to_dxl)} matched={matched} unmatched={unmatched} parse_errors={parse_errors}")
    print("preserved_old_columns=" + ",".join(sorted(OLD_PRIORITY_COLUMNS)))
    print("dxl_priority_columns=" + ",".join(DXL_PRIORITY_COLUMNS.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
