# fill_template.py
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple, Any

# from dxl_to_values import (
#     load_visible_field_names,
#     load_richtext_field_names,
#     dxl_to_values,
# )

# # ★あなたの配置に合わせて修正
# from dxl_attachments import extract_attachments_from_dxl
# from dxl_to_page_material import richtext_item_to_html_and_segment

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def _escape_value(v: str) -> str:
    s = html.escape(v, quote=False)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "<br/>")
    return s


def fill_template(
    *,
    template_html: str,
    values: Dict[str, str],
    raw_fields: Optional[Set[str]] = None,
) -> str:
    raw_fields = raw_fields or set()

    def repl(m: re.Match) -> str:
        key = m.group(1)
        v = values.get(key, "") or ""
        if key in raw_fields:
            return v
        return _escape_value(v)

    return _PLACEHOLDER_RE.sub(repl, template_html)


def iter_doc_dxl_paths(doc_dxl: Path) -> Iterable[Path]:
    if doc_dxl.is_file():
        yield doc_dxl
        return
    if not doc_dxl.is_dir():
        return
    for p in sorted(doc_dxl.glob("*.dxl")):
        name = p.name
        if "__FORM__" in name or "__SUBFORM__" in name:
            continue
        yield p


def load_template_and_fields(
    *,
    template_html_path: str | Path,
    fields_json_path: str | Path,
) -> tuple[str, Set[str], Set[str], Set[str]]:
    """
    戻り値:
      template_html,
      visible_names,
      richtext_names,
      raw_fields (= richtext_names)
    """
    template_path = Path(template_html_path)
    fields_path = Path(fields_json_path)

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    if not fields_path.exists():
        raise FileNotFoundError(f"Fields JSON not found: {fields_path}")

    template_html = template_path.read_text(encoding="utf-8")
    visible_names = load_visible_field_names(fields_path)
    richtext_names = load_richtext_field_names(fields_path)
    raw_fields = set(richtext_names)

    return template_html, visible_names, richtext_names, raw_fields


def dxl_to_richtext_html_values(
    dxl_path: str | Path,
    *,
    richtext_field_names: Set[str],
    seg_i_start: int = 1,
) -> Tuple[Dict[str, str], list[Any]]:
    """
    文書DXL 1件 → richtextフィールドだけHTML化して {name: html} を返す。
    segments も返す（OneNote multipart用）
    """
    dxl_path = Path(dxl_path)
    root = ET.parse(str(dxl_path)).getroot()

    attachment_objs_all = extract_attachments_from_dxl(str(dxl_path)) or []
    attachment_by_name = {a.filename: a for a in attachment_objs_all}

    out: Dict[str, str] = {}
    all_segments: list[Any] = []
    seg_i = seg_i_start

    for field_name in sorted(richtext_field_names):
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue
        if item.find("dxl:richtext", DXL_NS) is None:
            continue

        field_html, segment_list, seg_i = richtext_item_to_html_and_segment(
            item,
            attachment_by_name,
            seg_i=seg_i,
        )
        out[field_name] = field_html or ""
        all_segments.extend(segment_list)

    return out, all_segments


def build_filled_html_from_dxl(
    *,
    dxl_path: str | Path,
    template_html: str,
    visible_field_names: Set[str],
    richtext_field_names: Set[str],
    raw_fields: Optional[Set[str]] = None,
) -> tuple[str, Dict[str, str], list[Any]]:
    """
    外から呼ぶ本命関数。

    戻り値:
      filled_html,
      values(通常+richtext html),
      segments
    """
    dxl_path = Path(dxl_path)
    raw_fields = raw_fields or set(richtext_field_names)

    # 1) 通常フィールド（richtext除外）
    values = dxl_to_values(
        dxl_path,
        visible_field_names=visible_field_names,
        richtext_field_names=richtext_field_names,
    )

    # # 2) richtext（HTML化）を合流
    # rich_vals, segments = dxl_to_richtext_html_values(
    #     dxl_path,
    #     richtext_field_names=richtext_field_names,
    #     seg_i_start=1,
    # )
    # values.update(rich_vals)

    rich_vals = [],
    segments = [],

    # 3) テンプレへ埋め込み
    filled = fill_template(
        template_html=template_html,
        values=values,
        raw_fields=raw_fields,
    )

    return filled, values, segments


def build_filled_htmls_from_dir(
    *,
    doc_dxl_dir: str | Path,
    template_html: str,
    visible_field_names: Set[str],
    richtext_field_names: Set[str],
    raw_fields: Optional[Set[str]] = None,
) -> Iterable[tuple[Path, str, Dict[str, str], list[Any]]]:
    """
    ディレクトリ一括（ジェネレータ）
    yield: (dxl_file, filled_html, values, segments)
    """
    doc_dxl_dir = Path(doc_dxl_dir)
    for p in iter_doc_dxl_paths(doc_dxl_dir):
        filled, values, segs = build_filled_html_from_dxl(
            dxl_path=p,
            template_html=template_html,
            visible_field_names=visible_field_names,
            richtext_field_names=richtext_field_names,
            raw_fields=raw_fields,
        )
        yield p, filled, values, segs
