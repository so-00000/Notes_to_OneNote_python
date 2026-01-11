# graph_materialize.py（置き場所は client側でもOK）
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from .models import PagePayload, PendingPart, BinaryPart


# <div data-id='ph-xxx' data-filename='aaa.xlsx'></div>
_PH_RE = re.compile(
    r"<div\s+data-id=['\"](?P<phid>[^'\"]+)['\"]"
    r"(?:\s+data-filename=['\"](?P<fn>[^'\"]+)['\"])?\s*>\s*</div>",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GraphMaterialized:
    page_title: str
    body_html: str
    parts: list[BinaryPart]
    part_name_by_placeholder_id: dict[str, str]


def _img_html(part_name: str, p: PendingPart) -> str:
    style = "max-width:100%;"
    if getattr(p, "width", None):
        style += f" width:{p.width}px;"
    if getattr(p, "height", None):
        style += f" height:{p.height}px;"
    return (
        "<div style='margin:8px 0;'>"
        f"<img src='name:{html.escape(part_name)}' style='{style}'/>"
        "</div>"
    )


def _obj_html(part_name: str, filename: str, mime: str) -> str:
    fn = html.escape(filename, quote=True)
    mt = html.escape(mime or "application/octet-stream", quote=True)
    pn = html.escape(part_name, quote=True)
    return (
        "<div style='margin:8px 0; padding:10px; border:1px solid #e3e3e3; "
        "border-radius:10px; background:#fff;'>"
        f"<object data='name:{pn}' data-attachment='{fn}' type='{mt}'></object>"
        "</div>"
    )


def materialize_for_graph(
    payload: PagePayload,
    *,
    send_subset: Optional[Iterable[PendingPart]] = None,
) -> GraphMaterialized:
    """
    PagePayload（placeholder入りHTML + pending_parts）を、
    Graph送信用（name:attX 置換済みHTML + BinaryPart群）に変換する。

    B案（更新）前提：
    - send_subset に含まれない placeholder は HTML上 “そのまま残す”
      → 後で update 時に差し替え可能
    """
    # 今回送る分（指定がなければ全部）
    if send_subset is None:
        send = [p for p in payload.pending_parts if p is not None]
    else:
        send = [p for p in send_subset if p is not None]

    # placeholder_id -> att1/att2...
    part_name_by_phid = {p.placeholder_id: f"att{i}" for i, p in enumerate(send, start=1)}
    pending_by_phid = {p.placeholder_id: p for p in send}

    # HTML置換（送る分だけ置換。送らない分はdivを残す）
    def repl(m: re.Match) -> str:
        phid = m.group("phid")
        fn = m.group("fn") or ""

        p = pending_by_phid.get(phid)
        if not p:
            # 送らない placeholder → そのまま残す（B案のため）
            return m.group(0)

        part_name = part_name_by_phid[phid]

        if p.kind == "image":
            return _img_html(part_name, p)

        # attachment
        show_name = fn or p.filename
        return _obj_html(part_name, show_name, p.content_type)

    body_html = _PH_RE.sub(repl, payload.body_html)

    # BinaryPart化（Graph multipart の name と一致させる）
    parts: list[BinaryPart] = []
    for p in send:
        parts.append(
            BinaryPart(
                name=part_name_by_phid[p.placeholder_id],
                filename=p.filename,
                content_type=p.content_type,
                data=p.data,
                origin_field=p.origin_field,
            )
        )

    return GraphMaterialized(
        page_title=payload.page_title,
        body_html=body_html,
        parts=parts,
        part_name_by_placeholder_id=part_name_by_phid,
    )
