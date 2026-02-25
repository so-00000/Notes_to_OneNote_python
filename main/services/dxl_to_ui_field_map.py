# dxl_to_ui_field_map.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set

from main.renderers.common.util_render import _normalize_notes_dt

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}


# ------------------------------------------------------------
# DXL item から “テキスト値” を抽出（richtextはここでは扱わない）
# ------------------------------------------------------------
def _join_clean(values: List[str]) -> str:
    vals = [v.strip() for v in values if (v or "").strip()]
    vals = [re.sub(r"[ \t]+", " ", v) for v in vals]
    return "\n".join(vals)


def _extract_item_as_text(item: ET.Element) -> Optional[str]:
    """
    DXLの <item> 要素から “テキストとしての値” を抽出する。

    - richtext はここでは対象外（安全のため、見つかったら None を返す）
    - text / number / datetime の順に探す
    - 最後に fallback で itertxt を使う（ただし richtext が無い場合のみ）
    """
    # 念のため：richtextはここでは扱わない（別処理に任せる）
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


# ------------------------------------------------------------
# 画面表示フィールドだけを {name: value} にして返す
# ------------------------------------------------------------
def dxl_to_ui_field_map(
    root: ET.Element,
    *,
    visible_field_names: Set[str],
    richtext_field_names: Set[str],
) -> Dict[str, str]:
    """
    文書DXL 1件（root）→ 画面表示フィールドだけの {name: value} を返す。
    同名itemが複数ある場合は改行結合。

    - 画面表示フィールドのみ変換（visible_field_names）
    - 添付ファイル（$FILE）は除外
    - richtextフィールドは除外（richtext_field_names）
      ※richtextは別処理でHTML化して template などに埋め込む想定
    """
    out: Dict[str, str] = {}

    for item in root.findall(".//dxl:item", DXL_NS):
        name = item.get("name")
        if not name:
            continue

        # 添付ファイル除外
        if name == "$FILE":
            continue

        # 画面に表示しないフィールド除外
        if name not in visible_field_names:
            continue

        # richtextフィールド除外
        if name in richtext_field_names:
            continue

        # フィールド値を取得（テキストとして）
        v = _extract_item_as_text(item)
        if v is None:
            continue

        if name in out and out[name].strip():
            out[name] = out[name] + "\n" + v
        else:
            out[name] = v

    return out
