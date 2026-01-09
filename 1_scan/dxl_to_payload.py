# dxl_to_payload.py
from __future__ import annotations

import base64
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from dataclasses import dataclass
from typing import Optional, List, Tuple

from models import OneNoteRow
from dxl_to_model import dxl_to_onenote_row  # 既存

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}

@dataclass
class BinaryPart:
    name: str
    filename: str
    content_type: str
    data: bytes
    origin_field: str

_BINARY_TAG_TO_MIME = {
    "gif": "image/gif",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
}

def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag

def _safe_px(v: Optional[str]) -> Optional[int]:
    if not v:
        return None
    m = re.search(r"(\d+)", v)
    return int(m.group(1)) if m else None

def _richtext_item_to_html_and_parts(item_el: ET.Element, *, field_name: str, part_prefix: str) -> Tuple[str, List[BinaryPart]]:
    """
    <item name="Detail"> の <richtext> を
    - HTML（画像位置込み）
    - BinaryPart（画像バイナリ）
    に変換する（スクショ前提の最小実装）。
    """
    rt = item_el.find("dxl:richtext", DXL_NS)
    if rt is None:
        return "", []

    parts: List[BinaryPart] = []
    out: List[str] = []

    for par in rt.findall("dxl:par", DXL_NS):
        pic = par.find("dxl:picture", DXL_NS)
        if pic is not None:
            w = _safe_px(pic.get("width"))
            h = _safe_px(pic.get("height"))

            handled = False
            for child in list(pic):
                tag = _local_tag(child.tag)
                mime = _BINARY_TAG_TO_MIME.get(tag)
                if not mime:
                    continue

                b64 = (child.text or "").strip()
                if not b64:
                    continue

                data = base64.b64decode(b64)
                part_name = f"{part_prefix}{len(parts)+1}"
                filename = f"{part_name}.{tag}"

                parts.append(BinaryPart(
                    name=part_name,
                    filename=filename,
                    content_type=mime,
                    data=data,
                    origin_field=field_name,
                ))

                style = "max-width:100%;"
                if w:
                    style += f" width:{w}px;"
                if h:
                    style += f" height:{h}px;"

                out.append(
                    f"<div style='margin:8px 0;'><img src='name:{html.escape(part_name)}' style='{style}'/></div>"
                )
                handled = True
                break

            if not handled:
                out.append("<div style='color:#888;'>[画像（未対応形式）]</div>")
            continue

        # テキスト（最低限：par配下のテキストをescapeしてpで囲う）
        txt = "".join(par.itertext()).strip()
        if txt:
            out.append(f"<p>{html.escape(txt)}</p>")
        else:
            out.append("<p><br/></p>")

    return "\n".join(out), parts

def dxl_to_onenote_payload(dxl_path: str, *, rich_fields: List[str]) -> Tuple[OneNoteRow, List[BinaryPart]]:
    """
    DXL -> (OneNoteRow, 画像parts)
    - OneNoteRow: 文字フィールドは既存ロジック、rich_fieldsだけDXL直読みでHTMLに差し替え
    - parts: rich_fields内の <picture> を抽出してmultipart用に返す
    """
    note = dxl_to_onenote_row(dxl_path)
    root = ET.parse(dxl_path).getroot()

    parts_all: List[BinaryPart] = []
    replace_kwargs = {}

    for field_name in rich_fields:
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue

        field_html, parts = _richtext_item_to_html_and_parts(
            item,
            field_name=field_name,
            part_prefix=f"{field_name.lower()}_img_",
        )
        if field_html:
            replace_kwargs[field_name] = field_html
        parts_all.extend(parts)

    # frozen dataclass なので replace で差し替え
    if replace_kwargs:
        note = replace(note, **replace_kwargs)

    return note, parts_all
