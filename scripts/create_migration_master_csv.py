from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


MAPPING_ROOT = REPO_ROOT / "main" / "resources" / "mapping"
DOC_MAPPING_ROOT = REPO_ROOT / "main" / "doc_mapping"
COMMON_MAPPING_PATH = MAPPING_ROOT / "cmn_mapping.json"
_CSV_LINEBREAK_RE = re.compile(r"[\r\n]+")


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


def _read_rows_if_exists(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    return []


def _normalize_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return _CSV_LINEBREAK_RE.sub(" ", text).strip()


def _write_csv(csv_path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(
            [
                {h: _normalize_csv_cell(row.get(h, "")) for h in headers}
                for row in rows
            ]
        )


def _list_view_names() -> list[str]:
    return sorted(
        p.name
        for p in MAPPING_ROOT.iterdir()
        if p.is_dir() and (p / "mapping.json").exists()
    )


def _select_view_name_interactive(view_names: list[str]) -> str:
    print("Select view folder:")
    for i, name in enumerate(view_names, start=1):
        print(f"  {i}. {name}")

    while True:
        raw = input("Enter number: ").strip()
        if not raw.isdigit():
            print("Please input a number.")
            continue
        idx = int(raw)
        if 1 <= idx <= len(view_names):
            return view_names[idx - 1]
        print("Out of range.")


def _ask_overwrite() -> bool:
    raw = input("Overwrite existing rows (header-only recreate)? [y/N]: ").strip().lower()
    return raw in {"y", "yes"}


def main() -> int:
    if not COMMON_MAPPING_PATH.exists():
        raise FileNotFoundError(f"common mapping not found: {COMMON_MAPPING_PATH}")

    common_mapping = _load_json(COMMON_MAPPING_PATH)

    view_names = _list_view_names()
    if not view_names:
        print("[WARN] no view folders with mapping.json found.")
        return 0

    selected_view = _select_view_name_interactive(view_names)
    overwrite = _ask_overwrite()

    created = 0
    updated = 0
    skipped = 0

    mapping_path = MAPPING_ROOT / selected_view / "mapping.json"
    if not mapping_path.exists():
        print(f"[SKIP] mapping.json not found: {mapping_path}")
        skipped += 1
    else:
        view_mapping = _load_json(mapping_path)
        headers = _build_headers(common_mapping, view_mapping)
        csv_path = DOC_MAPPING_ROOT / selected_view / "migration_master.csv"
        existed_before = csv_path.exists()

        if csv_path.exists() and not overwrite:
            rows = _read_rows_if_exists(csv_path)
            _write_csv(csv_path, headers, rows)
            updated += 1
            print(f"[SYNC] {csv_path} rows={len(rows)} headers={len(headers)}")
        else:
            _write_csv(csv_path, headers, [])
            if existed_before:
                updated += 1
            else:
                created += 1
            print(f"[CREATE] {csv_path} headers={len(headers)}")

    print(
        f"[DONE] selected_view={selected_view} created={created} updated={updated} "
        f"skipped={skipped} overwrite={overwrite}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
