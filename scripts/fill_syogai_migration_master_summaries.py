from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.services.dxl_to_ui_field_map import dxl_to_field_map


CSV_PATH = REPO_ROOT / "main" / "doc_mapping" / "VwSyogai_11ALL" / "migration_master.csv"
DXL_ROOT = REPO_ROOT / "main" / "1_target_dxl" / "Fm_Document_2" / "result"
MISSING_IDS_PATH = REPO_ROOT / "main" / "doc_mapping" / "VwSyogai_11ALL" / "missing_dxl_unids.txt"

DXL_PRIORITY_DIR_ORDER = (
    "complete_障害DB_2016",
    "complete_障害DB_2017",
    "complete_障害DB_2018",
    "complete_障害DB_2019",
    "complete_障害DB_2020",
    "complete_障害DB_2021",
    "complete_障害DB_2022",
    "complete_障害DB_2023",
    "complete_障害DB_2024",
    "complete_BK",
    "duplicate",
    "error",
)
TARGET_FIELD_NAMES = {"DetailSubject", "ReasonSubject"}
CSV_LINEBREAK_RE = re.compile(r"[\r\n]+")


def _read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader.fieldnames or []), list(reader)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"unable to decode: {csv_path}")


def _normalize_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return CSV_LINEBREAK_RE.sub(" ", text).strip()


def _write_csv(csv_path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
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


def _extract_summaries(dxl_path: Path) -> dict[str, str]:
    root = ET.parse(dxl_path).getroot()
    return dxl_to_field_map(root, target_field_names=TARGET_FIELD_NAMES)


def _write_missing_ids(path: Path, missing_rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("unid\tsource_id\ttitle\n")
        for row in missing_rows:
            f.write(
                f"{row.get('unid', '')}\t{row.get('source_id', '')}\t{row.get('title', '')}\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill VwSyogai_11ALL migration_master.csv detailsubject/reasonsubject from DXL."
    )
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help=f"default: {CSV_PATH}")
    parser.add_argument("--dxl-root", type=Path, default=DXL_ROOT, help=f"default: {DXL_ROOT}")
    parser.add_argument(
        "--missing-ids-out",
        type=Path,
        default=MISSING_IDS_PATH,
        help=f"default: {MISSING_IDS_PATH}",
    )
    args = parser.parse_args()

    headers, rows = _read_csv_rows(args.csv)
    required_headers = {"unid", "detailsubject", "reasonsubject"}
    missing_headers = sorted(required_headers - set(headers))
    if missing_headers:
        raise ValueError(f"missing required headers in csv: {missing_headers}")

    unid_to_dxl = _build_unid_to_dxl_map(args.dxl_root)
    dxl_cache: dict[str, dict[str, str]] = {}

    updated_rows = 0
    rows_with_found_dxl = 0
    rows_with_missing_dxl = 0
    parse_errors = 0
    missing_dxl_rows: list[dict[str, str]] = []

    for row in rows:
        unid = row.get("unid", "").strip()
        if not unid:
            rows_with_missing_dxl += 1
            missing_dxl_rows.append(row)
            continue

        dxl_path = unid_to_dxl.get(unid)
        if dxl_path is None:
            rows_with_missing_dxl += 1
            missing_dxl_rows.append(row)
            continue

        if unid not in dxl_cache:
            try:
                dxl_cache[unid] = _extract_summaries(dxl_path)
            except ET.ParseError:
                parse_errors += 1
                dxl_cache[unid] = {}

        fields = dxl_cache[unid]
        rows_with_found_dxl += 1

        new_detail = fields.get("DetailSubject", "")
        new_reason = fields.get("ReasonSubject", "")
        if row.get("detailsubject", "") != new_detail or row.get("reasonsubject", "") != new_reason:
            row["detailsubject"] = new_detail
            row["reasonsubject"] = new_reason
            updated_rows += 1

    _write_csv(args.csv, headers, rows)
    _write_missing_ids(args.missing_ids_out, missing_dxl_rows)

    print(f"[DONE] csv={args.csv}")
    print(f"rows={len(rows)} updated_rows={updated_rows}")
    print(f"rows_with_found_dxl={rows_with_found_dxl}")
    print(f"rows_with_missing_dxl={rows_with_missing_dxl}")
    print(f"parse_errors={parse_errors}")
    print(f"missing_ids_out={args.missing_ids_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
