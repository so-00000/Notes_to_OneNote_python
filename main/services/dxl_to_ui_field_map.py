from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set

from main.renderers.common.util_render import _normalize_notes_dt

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}


def _join_clean(values: List[str]) -> str:
    vals = [v.strip() for v in values if (v or "").strip()]
    vals = [re.sub(r"[ \t]+", " ", v) for v in vals]
    return "\n".join(vals)


def _extract_item_as_text(item: ET.Element) -> Optional[str]:
    # RichText itself is rendered separately, so this text extractor skips it.
    if item.find("./dxl:richtext", DXL_NS) is not None:
        return None

    def _text_with_breaks(text_elem: ET.Element) -> str:
        parts: List[str] = []
        if text_elem.text:
            parts.append(text_elem.text)
        for child in list(text_elem):
            if child.tag == f"{{{DXL_NS['dxl']}}}break":
                parts.append("\n")
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    texts = [_text_with_breaks(t) for t in item.findall(".//dxl:text", DXL_NS)]
    if texts:
        s = _join_clean(texts)
        return s or None

    nums = [n.text or "" for n in item.findall(".//dxl:number", DXL_NS)]
    if nums:
        s = _join_clean(nums)
        return s or None

    dts = [
        _normalize_notes_dt("".join(dt.itertext()).strip())
        for dt in item.findall(".//dxl:datetime", DXL_NS)
    ]
    if dts:
        s = _join_clean(dts)
        return s or None

    fallback = "".join(item.itertext()).strip()
    if fallback and item.find(".//dxl:rawitemdata", DXL_NS) is not None:
        return None
    return fallback or None


def dxl_to_field_map(
    root: ET.Element,
    *,
    target_field_names: Set[str],
    richtext_field_names: Set[str] | None = None,
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    skip_richtext_field_names = richtext_field_names or set()

    for item in root.findall(".//dxl:item", DXL_NS):
        name = item.get("name")
        if not name or name == "$FILE":
            continue
        if name not in target_field_names:
            continue
        if name in skip_richtext_field_names:
            continue

        v = _extract_item_as_text(item)
        if v is None:
            continue

        if name in out and out[name].strip():
            out[name] = out[name] + "\n" + v
        else:
            out[name] = v

    return out


def dxl_to_ui_field_map(
    root: ET.Element,
    *,
    visible_field_names: Set[str],
    richtext_field_names: Set[str],
) -> Dict[str, str]:
    return dxl_to_field_map(
        root,
        target_field_names=visible_field_names,
        richtext_field_names=richtext_field_names,
    )
