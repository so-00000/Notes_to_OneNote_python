from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from main.models.models import PagePayload


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    for enc in ("cp932", "utf-8"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    return []


def _read_mapping(mapping_path: Path) -> Dict[str, object]:
    with mapping_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_common_mapping(mapping_path: Path) -> Dict[str, object]:
    common_path = mapping_path.parent.parent / "cmn_mapping.json"
    if not common_path.exists():
        return {"common_columns": []}
    with common_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_source_id(payload: PagePayload) -> str:
    replica_id = payload.doc_replicaid or ""
    unid = payload.doc_unid or ""
    return f"{replica_id}_{unid}" if replica_id and unid else ""


def find_row_by_source_id(csv_path: Path, source_id: str) -> Dict[str, str] | None:
    if not source_id:
        return None
    for row in _read_csv_rows(csv_path):
        if row.get("source_id", "") == source_id:
            return row
    return None


def delete_row_by_source_id(*, mapping_path: Path, csv_path: Path, source_id: str) -> int:
    if not csv_path.exists() or not source_id:
        return 0

    mapping = _read_mapping(mapping_path)
    common_mapping = _read_common_mapping(mapping_path)
    headers = _build_headers(mapping, common_mapping)
    rows = _read_csv_rows(csv_path)
    kept = [r for r in rows if r.get("source_id", "") != source_id]
    deleted = len(rows) - len(kept)
    if deleted <= 0:
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="cp932", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows([{h: r.get(h, "") for h in headers} for r in kept])
    return deleted


def _build_headers(mapping: Dict[str, object], common_mapping: Dict[str, object]) -> List[str]:
    common_keys = [c["key"] for c in common_mapping.get("common_columns", [])]
    headers = ["view_name", *common_keys]
    seen = set(headers)
    for view in mapping.get("views", {}).values():
        for col in view.get("view_columns", []):
            key = col.get("output_key")
            if key and key not in seen:
                headers.append(key)
                seen.add(key)
    return headers


def _select_view_columns(mapping: Dict[str, object]) -> List[Dict[str, object]]:
    views = mapping.get("views", {})
    if not views:
        return []
    first_view = next(iter(views.values()))
    return first_view.get("view_columns", [])


def upsert_migration_master(
    *,
    view_name: str,
    mapping_path: Path,
    csv_path: Path,
    payload: PagePayload,
    page_id: str = "",
    web_url: str = "",
    client_url: str = "",
    url_from_error: str = "",
    status: str,
    error_message: str = "",
    link_resolution_status: str = "",
) -> None:
    mapping = _read_mapping(mapping_path)
    common_mapping = _read_common_mapping(mapping_path)

    headers = _build_headers(mapping, common_mapping)
    view_columns = _select_view_columns(mapping)

    replica_id = payload.doc_replicaid or ""
    unid = payload.doc_unid or ""
    source_id = build_source_id(payload)

    row = {h: "" for h in headers}
    row["view_name"] = view_name
    row["source_id"] = source_id
    row["replica_id"] = replica_id
    row["unid"] = unid
    row["form"] = payload.extracted_fields.get("Form", "")
    row["title"] = payload.page_title or ""
    row["doc_date"] = (
        payload.extracted_fields.get("DocumentDate")
        or payload.extracted_fields.get("doc_date")
        or ""
    )
    row["onenote_page_id"] = page_id
    row["onenote_web_url"] = web_url
    row["onenote_client_url"] = client_url
    row["url_from_error"] = url_from_error
    row["migration_status"] = status
    row["error_message"] = error_message
    row["link_resolution_status"] = link_resolution_status
    row["processed_at"] = datetime.now().isoformat(timespec="seconds")

    for col in view_columns:
        output_key = col.get("output_key")
        item_name = col.get("item_name", "")
        if output_key and output_key in row:
            row[output_key] = payload.extracted_fields.get(item_name, "")

    rows = _read_csv_rows(csv_path)
    updated = False
    if source_id:
        for i, existing in enumerate(rows):
            if existing.get("source_id", "") == source_id:
                rows[i] = {h: row.get(h, existing.get(h, "")) for h in headers}
                updated = True
                break
    if not updated:
        rows.append({h: row.get(h, "") for h in headers})

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="cp932", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows([{h: r.get(h, "") for h in headers} for r in rows])
