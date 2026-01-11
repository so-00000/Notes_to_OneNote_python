# dxl_to_payload.py
from __future__ import annotations

import base64
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from typing import Optional, Tuple

from .models import OneNoteRow
from .dxl_to_model import dxl_to_onenote_row  # 既存
from .dxl_attachments import extract_attachments_from_dxl  # 追加
from .models import PendingPart
from .config import RICH_FIELDS
from typing import Any
import logging
logger = logging.getLogger(__name__)




DXL_NS = {"dxl": "http://www.lotus.com/dxl"}

# DXL内の画像タグ名 -> MIMEタイプ
_BINARY_TAG_TO_MIME = {
    "gif": "image/gif",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
}


def _local_tag(tag: str) -> str:
    """タグのローカル名だけ返す（XMLの名前空間を削除）"""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _safe_px(v: Optional[str]) -> Optional[int]:
    """px表記や数値文字列から幅/高さを安全に抽出する。"""
    if not v:
        return None
    m = re.search(r"(\d+)", v)
    return int(m.group(1)) if m else None


def _par_text_without_binary(par: ET.Element) -> str:
    """
    par 内のテキストを取るが、バイナリ系/添付参照系は本文に混ぜない。
    ※ attachmentref はファイル名などが入っていても、object化するので本文には出さない
    """
    skip = {
        "picture",
        "notesbitmap",
        "gif",
        "png",
        "jpeg",
        "jpg",
        "filedata",
        "attachmentref",
    }

    def walk(el: ET.Element) -> str:
        tag = _local_tag(el.tag)
        if tag in skip:
            return el.tail or ""

        s = el.text or ""
        for ch in list(el):
            s += walk(ch)
        s += el.tail or ""
        return s

    return re.sub(r"\s+\n", "\n", walk(par)).strip()



def _sanitize_id(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "field"

def _make_ph_id(field_name: str, kind: str, idx: int) -> str:
    return f"ph-{_sanitize_id(field_name)}-{kind}-{idx:03d}"

def _ph_div(ph_id: str, *, filename: str | None = None) -> str:
    if filename:
        fn = html.escape(filename, quote=True)
        return f"<div data-id='{ph_id}' data-filename='{fn}'></div>"
    return f"<div data-id='{ph_id}'></div>"



# picture要素からHTML（マーカー込み）・バイナリデータを作成する
def _picture_to_html_and_pending(
    pic: ET.Element,
    *,
    field_name: str,
    img_index: int,
) -> tuple[str, PendingPart | None]:
    w = _safe_px(pic.get("width"))
    h = _safe_px(pic.get("height"))

    ph_id = _make_ph_id(field_name, "img", img_index)

    for child in list(pic):
        tag = _local_tag(child.tag)
        mime = _BINARY_TAG_TO_MIME.get(tag)
        if not mime:
            continue

        b64 = (child.text or "").strip()
        if not b64:
            continue

        try:
            data = base64.b64decode(b64)
        except Exception:
            return _ph_div(ph_id), None

        filename = f"{ph_id}.{tag}"
        pending = PendingPart(
            placeholder_id=ph_id,
            kind="image",
            filename=filename,
            content_type=mime,
            data=data,
            origin_field=field_name,
            width=w,
            height=h,
        )
        return _ph_div(ph_id), pending

    # 画像の形式が未対応でも位置は残す
    return _ph_div(ph_id), None



def _attref_to_placeholder_and_pending(
    *,
    field_name: str,
    att_index: int,
    filename: str,
    attachment_by_name: dict[str, Any],   # extract_attachments_from_dxl が返すオブジェクト
) -> tuple[str, PendingPart | None]:
    ph_id = _make_ph_id(field_name, "att", att_index)
    html_ph = _ph_div(ph_id, filename=filename)

    a = attachment_by_name.get(filename)
    if not a:
        # 実体ないので placeholder は残すが pending は None
        return html_ph, None

    pending = PendingPart(
        placeholder_id=ph_id,
        kind="attachment",
        filename=a.filename,
        content_type=a.mime or "application/octet-stream",
        data=a.content,
        origin_field="$FILE",
    )
    return html_ph, pending



def _table_to_html(table_el: ET.Element) -> str:
    """
    richtext 内の <table> をシンプルに HTML table に変換する（テキストのみ）。
    - セル内の画像/添付(ref)は想定しない（あっても無視）
    - 余計な装飾は最低限
    """
    rows: list[str] = []

    # DXL: <table> -> <tablerow> -> <tablecell>
    tablerows = table_el.findall("dxl:tablerow", DXL_NS)
    for tr in tablerows:
        cells_html: list[str] = []
        cells = tr.findall("dxl:tablecell", DXL_NS)

        for td in cells:
            # セル内テキスト（子孫含めて全部）を取得
            txt = "".join(td.itertext()).strip()
            txt = re.sub(r"\s+\n", "\n", txt)
            safe = html.escape(txt).replace("\n", "<br/>") if txt else ""
            cells_html.append(
                f"<td style='border:1px solid #ddd; padding:6px; vertical-align:top;'>{safe}</td>"
            )

        rows.append("<tr>" + "".join(cells_html) + "</tr>")

    # 全体を軽く囲う（見やすさ用）
    return (
        "<div style='margin:10px 0;'>"
        "<table style='border-collapse:collapse; width:100%;'>"
        + "".join(rows)
        + "</table>"
        "</div>"
    )



def richtext_item_to_html_and_pending(
    item_el: ET.Element,    # DXLのitem要素
    attachment_by_name: dict[str, Any],
) -> tuple[str, list[PendingPart], dict[str, PendingPart]]:
    
    # フィールド名取得
    field_name = (item_el.get("name") or "unknown").strip()

    # 実際にリッチテキストが入っていなければ処理をスキップ（消していいかも）
    rt = item_el.find("dxl:richtext", DXL_NS)
    if rt is None:
        logger.warning("richtext not found. skip field=%s", field_name)
        return "", [], {}



    # 返却するHTML要素
    out: list[str] = []
    # バイナリデータ（添付ファイル / 画像など）のリスト
    pending_list: list[PendingPart] = []

    # 画像ファイル連番
    img_i = 1
    # 添付ファイル連番
    att_i = 1

    for child in list(rt):
        tag = _local_tag(child.tag)

        # 「parタグ」の走査
        if tag == "par":
            par = child

            # 添付ファイル
            attrefs = par.findall(".//dxl:attachmentref", DXL_NS)

            if attrefs:
                # ラベル作成
                label = _par_text_without_binary(par)
                if label:
                    # ラベルを埋め込んだHTML作成
                    out.append(f"<p>{html.escape(label)}</p>")

                for a in attrefs:
                    fn = (a.get("displayname") or a.get("name") or "").strip()
                    if not fn:
                        continue
                    ph_html, pending = _attref_to_placeholder_and_pending(
                        field_name=field_name,
                        att_index=att_i,
                        filename=fn,
                        attachment_by_name=attachment_by_name,
                    )
                    out.append(ph_html)
                    if pending:
                        pending_list.append(pending)
                    att_i += 1
                continue

            # 画像データ（キャプチャ）の走査
            pic = par.find(".//dxl:picture", DXL_NS)

            if pic is not None:
                # HTML（マーカー込み）・バイナリデータの作成
                ph_html, pending = _picture_to_html_and_pending(
                    pic, field_name=field_name, img_index=img_i
                )

                # HTML追加
                if pending:
                    pending_list.append(pending)


                # バイナリリスト追加
                pending_list.append(pending)
 
                img_i += 1

                continue

            # テキストの走査
            txt = _par_text_without_binary(par)
            out.append(f"<p>{html.escape(txt)}</p>" if txt)
            continue


        # 「tableタグ」の走査
        if tag == "table":
            table_html = _table_to_html(child)
            out.append(table_html)




    ph_map = {p.placeholder_id: p for p in pending_list}

    return "\n".join(out), pending_list, ph_map



def create_contents_from_dxl(
    dxl_path: str,
) -> tuple[OneNoteRow, list[PendingPart], dict[str, PendingPart]]:

    all_pending: list[PendingPart] = []
    all_map: dict[str, PendingPart] = {}


    # 1件分の全データ取得
    note = dxl_to_onenote_row(dxl_path)
    root = ET.parse(dxl_path).getroot()

    # 添付ファイル（$FILE）全件を抽出
    attachment_objs_all = extract_attachments_from_dxl(dxl_path) or []
    attachment_by_name = {a.filename: a for a in attachment_objs_all}

    # RichTextフィールドに対して下記を行う
    # ・HTML変換
    # ・埋め込みファイル（キャプチャ画像やExcelなど）の抽出
    for field_name in RICH_FIELDS:

        # 対象フィールド（型：RichText）をセット
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue

        # フィールド（RichText）から下記を取得
        # 変換後HTML
        # バイナリデータ一時リスト
        # バイナリデータ変換リスト
        field_html, pending_list, ph_map = richtext_item_to_html_and_pending(
            item,
            attachment_by_name,
        )

        if field_html:
            setattr(note, field_name, field_html)

        all_pending.extend(pending_list)
        all_map.update(ph_map)

    # note側には全添付名だけ残す（メタとして）
    if attachment_objs_all:
        note.attachments = [a.filename for a in attachment_objs_all]

    return note, all_pending, all_map