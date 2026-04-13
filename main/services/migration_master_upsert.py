from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from main.models.models import PagePayload


_CSV_LINEBREAK_RE = re.compile(r"[\r\n]+")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    for enc in ("utf-8", "utf-8-sig", "cp932"):
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


def _normalize_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return _CSV_LINEBREAK_RE.sub(" ", text).strip()


def _strip_outer_parens(expr: str) -> str:
    text = expr.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        in_string = False
        balanced = True
        for idx, ch in enumerate(text):
            if ch == '"' and (idx == 0 or text[idx - 1] != "\\"):
                in_string = not in_string
            elif not in_string:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and idx != len(text) - 1:
                        balanced = False
                        break
        if balanced and depth == 0:
            text = text[1:-1].strip()
        else:
            break
    return text


def _split_top_level(expr: str, delimiter: str) -> List[str]:
    parts: List[str] = []
    start = 0
    depth = 0
    in_string = False

    for idx, ch in enumerate(expr):
        if ch == '"' and (idx == 0 or expr[idx - 1] != "\\"):
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            continue
        if ch == delimiter and depth == 0:
            parts.append(expr[start:idx].strip())
            start = idx + 1

    parts.append(expr[start:].strip())
    return parts


def _parse_string_literal(expr: str) -> str | None:
    text = expr.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('""', '"')
    return None


def _evaluate_formula(expr: str, values: Dict[str, str]) -> str:
    text = _strip_outer_parens(expr.strip())
    if not text:
        return ""

    literal = _parse_string_literal(text)
    if literal is not None:
        return literal

    concat_parts = _split_top_level(text, "+")
    if len(concat_parts) > 1:
        return "".join(_evaluate_formula(part, values) for part in concat_parts)

    lowered = text.lower()
    if lowered.startswith("@text(") and text.endswith(")"):
        inner = text[text.find("(") + 1 : -1]
        return _evaluate_formula(inner, values)

    if lowered.startswith("@right(") and text.endswith(")"):
        inner = text[text.find("(") + 1 : -1]
        args = _split_top_level(inner, ";")
        if len(args) != 2:
            return ""
        value = _evaluate_formula(args[0], values)
        length_text = _evaluate_formula(args[1], values)
        try:
            length = int(length_text)
        except ValueError:
            return ""
        return value[-length:] if length >= 0 else ""

    if lowered.startswith("@if(") and text.endswith(")"):
        inner = text[text.find("(") + 1 : -1]
        args = _split_top_level(inner, ";")
        if len(args) < 3:
            return ""

        pair_count = len(args) - 1
        for idx in range(0, pair_count, 2):
            if idx + 1 >= len(args):
                break
            if _evaluate_formula_condition(args[idx], values):
                return _evaluate_formula(args[idx + 1], values)
        if len(args) % 2 == 1:
            return _evaluate_formula(args[-1], values)
        return ""

    if text.isdigit():
        return text

    if _IDENTIFIER_RE.match(text):
        return str(values.get(text, ""))

    return str(values.get(text, ""))


def _evaluate_formula_condition(expr: str, values: Dict[str, str]) -> bool:
    text = _strip_outer_parens(expr.strip())
    if not text:
        return False

    depth = 0
    in_string = False
    for idx, ch in enumerate(text):
        if ch == '"' and (idx == 0 or text[idx - 1] != "\\"):
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(depth - 1, 0)
            continue
        if ch == "=" and depth == 0:
            left = text[:idx].strip()
            right = text[idx + 1 :].strip()
            return _evaluate_formula(left, values) == _evaluate_formula(right, values)

    return _evaluate_formula(text, values) not in {"", "0"}


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
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(
            [
                {h: _normalize_csv_cell(r.get(h, "")) for h in headers}
                for r in kept
            ]
        )
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
    migration_master_map = payload.migration_master_map or {}
    row["view_name"] = view_name
    row["source_id"] = source_id
    row["replica_id"] = replica_id
    row["unid"] = unid
    row["form"] = migration_master_map.get("Form") or payload.extracted_fields.get("Form", "")
    row["title"] = payload.page_title or ""
    row["doc_date"] = (
        migration_master_map.get("DocumentDate")
        or payload.extracted_fields.get("DocumentDate")
        or migration_master_map.get("doc_date")
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

    formula_values: Dict[str, str] = {}
    formula_values.update(payload.extracted_fields)
    formula_values.update(migration_master_map)

    for col in view_columns:
        output_key = str(col.get("output_key") or "").strip()
        item_name = str(col.get("item_name") or "").strip()
        formula = str(col.get("formula") or "").strip()
        if output_key and output_key in row:
            value = ""
            if item_name:
                value = migration_master_map.get(
                    item_name,
                    payload.extracted_fields.get(item_name, ""),
                )
            if (not value) and formula:
                value = _evaluate_formula(formula, formula_values)
            row[output_key] = value
            formula_values[output_key] = str(value)

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
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(
            [
                {h: _normalize_csv_cell(r.get(h, "")) for h in headers}
                for r in rows
            ]
        )
