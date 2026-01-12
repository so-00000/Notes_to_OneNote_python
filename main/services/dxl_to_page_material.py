# dxl_to_page_material.py
from __future__ import annotations

import base64
import html
import re
import xml.etree.ElementTree as ET
from typing import Optional

from ..models import OneNoteRow
from ..dxl_to_model import dxl_to_onenote_row
from ..dxl_attachments import extract_attachments_from_dxl
from ..models import Segment, BinaryPart
from ..config import RICH_FIELDS
from typing import Any
from pprint import pprint
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


def make_anchor(seg_id: str) -> str:
    sid = html.escape(seg_id, quote=True)
    return f"<div id='{sid}' data-id='{sid}'></div>"



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
    par 内のテキストのみ抽出（バイナリの文字列削除）
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



# 添付ファイル要素からセグメントデータを作成する
def _attref_to_segment(
    *,
    filename: str,
    field_name: str,
    segment_id: str,
    attachment_by_name: dict[str, Any],
) -> Segment | None:
    a = attachment_by_name.get(filename)
    if not a:
        # 実体が無いなら埋め込みできない（アンカーは残る）
        return None

    binary = BinaryPart(
        kind="attachment",
        filename=a.filename,
        content_type=(a.mime or "application/octet-stream"),
        data=a.content,
        origin_field="$FILE",
    )
    return Segment(segment_id=segment_id, kind="attachment", binary_part=binary)



# picture要素からセグメントデータを作成する
def _picture_to_segment(
    pic: ET.Element,
    *,
    field_name: str,
    seg_id: str,
) -> Segment | None:
    w = _safe_px(pic.get("width"))
    h = _safe_px(pic.get("height"))

    # 画像バイナリの取り出し
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
            return None

        filename = f"{seg_id}.{tag}"

        binary = BinaryPart(
            kind="image",
            filename=filename,
            content_type=mime,
            data=data,
            origin_field=field_name,
            width=w,
            height=h,
        )
        return Segment(segment_id=seg_id, kind="image", binary_part=binary)

    return None



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



def richtext_item_to_html_and_segment(
    item_el: ET.Element,    # DXLのitem要素
    attachment_by_name: dict[str, Any],
    *,
    seg_i: int,
) -> tuple[str, list[Segment], int]:
    
    # フィールド名取得
    field_name = (item_el.get("name") or "unknown").strip()

    # 実際にリッチテキストが入っていなければ処理をスキップ（消していいかも）
    rt = item_el.find("dxl:richtext", DXL_NS)
    if rt is None:
        logger.warning("richtext not found. skip field=%s", field_name)
        return "", [], seg_i




    # 返却するHTML要素
    out: list[str] = []
    # セグメントデータ（バイナリデータを内包）のリスト
    segment_list: list[Segment] = []

    for child in list(rt):
        tag = _local_tag(child.tag)

        # 「parタグ」の走査
        if tag == "par":
            par = child

            # 添付ファイル
            attrefs = par.findall(".//dxl:attachmentref", DXL_NS)

            if attrefs:
                for a in attrefs:
                    fn = (a.get("displayname") or a.get("name") or "").strip()
                    if not fn:
                        continue

                    # セグメントIDの作成
                    seg_id = f"seg-{seg_i:03d}"

                    # セグメントアンカーの埋め込み（後続処理でBinaryデータを含むHTMLに置換）
                    out.append(make_anchor(seg_id))

                    # セグメントデータの作成
                    seg = _attref_to_segment(
                        filename=fn,
                        field_name=field_name,
                        segment_id=seg_id,
                        attachment_by_name=attachment_by_name,
                    )

                    if seg:
                        segment_list.append(seg)

                    seg_i += 1

                continue



            # 画像データ（キャプチャ）の走査
            pic = par.find(".//dxl:picture", DXL_NS)

            if pic is not None:

                # セグメントIDの作成
                seg_id = f"seg-{seg_i:03d}"

                # セグメントアンカーの埋め込み（後続処理でBinaryデータを含むHTMLに置換）
                out.append(make_anchor(seg_id))

                # セグメントデータの作成
                seg = _picture_to_segment(
                    pic,
                    field_name=field_name,
                    seg_id=seg_id,
                )

                if seg:
                    segment_list.append(seg)

                seg_i += 1

                continue

            # テキストの走査
            txt = _par_text_without_binary(par)
            out.append(f"<p>{html.escape(txt)}</p>")
            continue


        # 「tableタグ」の走査
        if tag == "table":
            table_html = _table_to_html(child)
            out.append(table_html)

    return "\n".join(out), segment_list, seg_i



def create_materials_from_dxl(
    dxl_path: str,
) -> tuple[OneNoteRow, list[Segment]]:

    all_segment: list[Segment] = []


    # 1件分の全データ取得
    note = dxl_to_onenote_row(dxl_path)
    root = ET.parse(dxl_path).getroot()

    # 添付ファイル（$FILE）全件を抽出
    attachment_objs_all = extract_attachments_from_dxl(dxl_path) or []
    attachment_by_name = {a.filename: a for a in attachment_objs_all}


    # セグメント連番
    seg_i = 1


    # RichTextフィールドに対して下記を行う
    # ・HTML変換
    # ・埋め込みファイル（キャプチャ画像やExcelなど）の抽出
    for field_name in RICH_FIELDS:

        # 対象フィールド（型：RichText）をセット
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue

        # フィールド（RichText）から下記を取得
        # 変換後HTML（segment_id付与）
        # バイナリデータ一時リスト
        field_html, segment_list, seg_i = richtext_item_to_html_and_segment(
            item,
            attachment_by_name,
            seg_i=seg_i,
        )

        setattr(note, field_name, field_html or "")

        all_segment.extend(segment_list)

    # note側には全添付名だけ残す（メタとして）
    if attachment_objs_all:
        note.attachments = [a.filename for a in attachment_objs_all]


    for s in all_segment:
        print(s.segment_id)


    return note, all_segment
