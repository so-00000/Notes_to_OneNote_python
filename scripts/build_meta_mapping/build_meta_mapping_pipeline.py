from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

BASE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = BASE_DIR / "source_view"
MAPPING_ROOT = (BASE_DIR / "../../main/resources/mapping").resolve()
COMMON_MAPPING_PATH = MAPPING_ROOT / "cmn_mapping.json"

COMMON_COLUMNS: List[Dict[str, str]] = [
    {"key": "source_id", "meaning": "unique key: replica_id + '_' + unid", "source": "computed"},
    {"key": "replica_id", "meaning": "Notes DB identifier", "source": "Notes/DXL/config"},
    {"key": "unid", "meaning": "Notes document UNID", "source": "Notes/DXL"},
    {"key": "form", "meaning": "form name", "source": "Notes item Form"},
    {"key": "title", "meaning": "page title", "source": "Notes item or rule"},
    {"key": "doc_date", "meaning": "sort base date", "source": "Notes item or rule"},
    {"key": "onenote_page_id", "meaning": "OneNote page id", "source": "Graph response"},
    {"key": "onenote_web_url", "meaning": "web url", "source": "Graph links.oneNoteWebUrl.href"},
    {"key": "onenote_client_url", "meaning": "client url", "source": "Graph links.oneNoteClientUrl.href"},
    {"key": "url_from_error", "meaning": "url extracted from error", "source": "error parsing"},
    {"key": "migration_status", "meaning": "migration result status", "source": "migration process"},
    {"key": "error_message", "meaning": "error message", "source": "exception/response"},
    {"key": "processed_at", "meaning": "processed timestamp", "source": "migration process"},
    {"key": "link_resolution_status", "meaning": "link resolution status", "source": "link resolver"},
]


@dataclass
class ViewColumn:
    column_index: int
    column_title: str
    item_name: str
    formula: str
    is_category: bool
    is_hidden: bool
    output_key: str


@dataclass
class ViewPaths:
    view_folder: str
    source_dir: Path
    mapping_path: Path


def _read_view_csv(csv_path: Path) -> List[Dict[str, str]]:
    for enc in ("cp932", "utf-8"):
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"could not decode: {csv_path}")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_]", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "col"


def _bool_text(v: str) -> bool:
    return str(v).strip() in {"1", "true", "True", "TRUE"}


def _build_view_columns(rows: Sequence[Dict[str, str]]) -> List[ViewColumn]:
    cols: List[ViewColumn] = []
    seen_keys: Dict[str, int] = {}
    for row in sorted(rows, key=lambda r: int(r.get("ColumnIndex") or 0)):
        title = (row.get("ColumnTitle") or "").strip()
        item_name = (row.get("ItemName") or "").strip()
        base_key = _slugify(item_name or title or f"col_{row.get('ColumnIndex', '')}")
        seen_keys[base_key] = seen_keys.get(base_key, 0) + 1
        output_key = base_key if seen_keys[base_key] == 1 else f"{base_key}_{seen_keys[base_key]}"
        cols.append(
            ViewColumn(
                column_index=int(row.get("ColumnIndex") or 0),
                column_title=title,
                item_name=item_name,
                formula=(row.get("Formula") or "").strip(),
                is_category=_bool_text(row.get("IsCategory", "")),
                is_hidden=_bool_text(row.get("IsHidden", "")),
                output_key=output_key,
            )
        )
    return cols


def _list_view_folders() -> List[str]:
    if not SOURCE_ROOT.exists():
        return []
    return sorted([p.name for p in SOURCE_ROOT.iterdir() if p.is_dir()])


def _select_view_folder(cli_view: str | None) -> str:
    folders = _list_view_folders()
    if not folders:
        raise FileNotFoundError(f"No view folders found under: {SOURCE_ROOT}")

    if cli_view:
        if cli_view not in folders:
            raise ValueError(f"View folder not found: {cli_view}")
        return cli_view

    if len(folders) == 1:
        print(f"Target view: {folders[0]} (single folder)")
        return folders[0]

    print("Select target view folder:")
    for i, name in enumerate(folders, start=1):
        print(f"  {i}. {name}")

    while True:
        answer = input("Enter number: ").strip()
        if answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(folders):
                return folders[idx - 1]
        print("Invalid input. Enter a number from the list.")


def _resolve_paths(view_folder: str) -> ViewPaths:
    return ViewPaths(
        view_folder=view_folder,
        source_dir=SOURCE_ROOT / view_folder,
        mapping_path=MAPPING_ROOT / view_folder / "mapping.json",
    )


def generate_mapping(paths: ViewPaths) -> Dict[str, object]:
    csv_files = sorted(paths.source_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No source CSV found: {paths.source_dir}")

    views: Dict[str, Dict[str, object]] = {}
    for csv_file in csv_files:
        rows = _read_view_csv(csv_file)
        if not rows:
            continue
        view_name = (rows[0].get("ViewName") or csv_file.stem).strip()
        cols = _build_view_columns(rows)
        views[view_name] = {
            "source_csv": csv_file.name,
            "view_columns": [
                {
                    "column_index": c.column_index,
                    "column_title": c.column_title,
                    "item_name": c.item_name,
                    "formula": c.formula,
                    "is_category": c.is_category,
                    "is_hidden": c.is_hidden,
                    "output_key": c.output_key,
                }
                for c in cols
            ],
        }

    mapping = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "view_folder": paths.view_folder,
        "views": views,
    }
    paths.mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.mapping_path.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    return mapping


def write_common_mapping() -> None:
    common = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "common_columns": COMMON_COLUMNS,
    }
    COMMON_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COMMON_MAPPING_PATH.open("w", encoding="utf-8") as f:
        json.dump(common, f, ensure_ascii=False, indent=2)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate mapping.json metadata from source view CSV files.")
    parser.add_argument("--view", type=str, default=None, help="Target view folder under source_view")
    parser.add_argument(
        "command",
        nargs="?",
        default="build",
        choices=["build", "generate-mapping", "list-views"],
        help="build/generate-mapping/list-views",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "list-views":
        for name in _list_view_folders():
            print(name)
        return

    view_folder = _select_view_folder(args.view)
    paths = _resolve_paths(view_folder)

    write_common_mapping()
    mapping = generate_mapping(paths)
    print(f"view_folder: {paths.view_folder}")
    print(f"mapping.json generated: {paths.mapping_path} (views={len(mapping['views'])})")
    print(f"common mapping generated: {COMMON_MAPPING_PATH}")


if __name__ == "__main__":
    main()
