# extract_attachments.py
from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from typing import Optional
import xml.etree.ElementTree as ET
from pprint import pprint


DXL_NS = {"dxl": "http://www.lotus.com/dxl"}


@dataclass
class DxlAttachment:
    filename: str
    mime: str
    content: bytes


def _guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        return mime
    fn = filename.lower()
    if fn.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fn.endswith(".xls"):
        return "application/vnd.ms-excel"
    if fn.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


def _extract_attachments(root: ET.Element) -> list[DxlAttachment]:
    """
    root から $FILE の添付を抽出する（DXLのroot版）。
    返すオブジェクトは .filename .mime .content を持つ。
    """
    out: list[DxlAttachment] = []

    # $FILE item配下の <file> を取得
    files = root.findall(".//dxl:item[@name='$FILE']//dxl:file", DXL_NS)

    for f in files:
        # file要素の属性 name がファイル名
        filename = (f.get("name") or "").strip() or "attachment.bin"

        # filedata（base64）を取得
        fd = f.find("dxl:filedata", DXL_NS)
        if fd is None:
            # DXLによっては別構造の可能性もあるので、子孫から探す
            fd = f.find(".//dxl:filedata", DXL_NS)
        if fd is None:
            continue

        b64 = re.sub(r"\s+", "", "".join(fd.itertext()).strip())
        if not b64:
            continue

        try:
            content = base64.b64decode(b64)
        except Exception:
            # 壊れた添付はスキップ
            continue

        out.append(
            DxlAttachment(
                filename=filename,
                mime=_guess_mime(filename),
                content=content,
            )
        )

    return out
