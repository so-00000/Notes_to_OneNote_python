# dxl_attachments.py
from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lxml import etree


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


def extract_attachments_from_dxl(dxl_path: str | Path) -> list[DxlAttachment]:
    dxl_path = Path(dxl_path)
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.parse(str(dxl_path), parser).getroot()

    ns = {"d": "http://www.lotus.com/dxl"}
    items = root.xpath(".//d:item[@name='$FILE']", namespaces=ns)

    out: list[DxlAttachment] = []
    for it in items:
        f = it.find(".//{http://www.lotus.com/dxl}file")
        fd = it.find(".//{http://www.lotus.com/dxl}filedata")
        if f is None or fd is None:
            continue

        filename = f.get("name") or "attachment.bin"
        b64 = re.sub(r"\s+", "", "".join(fd.itertext()))
        content = base64.b64decode(b64)  # xlsxなら先頭が b'PK\x03\x04' になる

        out.append(
            DxlAttachment(
                filename=filename,
                mime=_guess_mime(filename),
                content=content,
            )
        )
    return out
