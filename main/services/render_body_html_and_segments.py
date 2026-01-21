# dxl_to_page_material.py
from __future__ import annotations

import base64
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

from main.data_type_config import get_data_type_settings
# from main.dxl_to_model import dxl_to_onenote_row
from main.services.extract_attachments import _extract_attachments
from main.services.fill_template import fill_template
from main.models.models import Segment, BinaryPart
from pprint import pprint
import logging
import re
import html

logger = logging.getLogger(__name__)


def _resolve_path(value: str | Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / p).resolve()




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



def _detect_richtext_field_names(root: ET.Element, data_type: Any) -> Set[str]:
    """
    richtextフィールド名を決める。
    - data_type.rich_fields があればそれを優先
    - なければ DXL上で richtext を持つ item を自動検出（type=="richtext" 相当）
    """
    rf = getattr(data_type, "rich_fields", None)
    if rf:
        return {str(x) for x in rf}

    out: Set[str] = set()
    for item in root.findall(".//dxl:item", DXL_NS):
        name = item.get("name")
        if not name or name == "$FILE":
            continue
        if item.find("dxl:richtext", DXL_NS) is not None:
            out.add(name)
    return out



def render_body_html_and_segments(
    *,
    root: ET.Element,
    ui_field_map: Dict[str, str],
    data_type: Any,
    rich_field_names: str
) -> Tuple[str, List[Segment]]:
    """
    root（DXLをET.parseしてgetrootしたもの）を受け取り、
    - body_html（テンプレに埋め込み済みHTML）
    - segment_list（画像/添付の埋め込み用Segment）
    を返す。

    前提:
    - ui_field_map は「画面表示項目（richtext除外）」の辞書
    - richtext はここで HTML化して values にマージし、raw_fields としてエスケープせず埋め込む
    """

    # 添付（$FILE）を root から抽出して参照用mapに変換
    attachment_objs_all = _extract_attachments(root) or []
    attachment_map = {obj.filename: obj for obj in attachment_objs_all if getattr(obj, "filename", None)}
    
    print("🪅🪅🪅attachments:", len(attachment_map))
    print("🪅🪅🪅names:", list(attachment_map.keys()))



    # セグメント連番
    seg_i = 1
    all_segments: List[Segment] = []
    rich_map: Dict[str, str] = {}


    # RichTextフィールドに対して下記を行う
    # ・HTML変換
    # ・埋め込みファイル（キャプチャ画像やExcelなど）の抽出
    for field_name in rich_field_names:

        # 対象フィールド（型：RichText）をセット
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue
        if item.find("dxl:richtext", DXL_NS) is None:
            continue

        # フィールド（RichText）から下記を取得
        # 変換後HTML（segment_id付与）
        # バイナリデータ一時リスト
        field_html, seg_list, seg_i = richtext_item_to_html_and_segment(
            item,
            attachment_map,
            seg_i=seg_i,
        )

        rich_map[field_name] = field_html or ""
        all_segments.extend(seg_list)

        
    # テンプレ埋め込み用 values を作る（ui_field_map + rich_map）
    values: Dict[str, str] = dict(ui_field_map)
    values.update(rich_map)
    pprint("🪅🪅🪅:rich_map")
    pprint(rich_map)


    # HTMLテンプレートの読み込み（data_typeで切替）
    template_html_path = _resolve_path(data_type.template_html_path)

    pprint("🪅🪅🪅")
    pprint(template_html_path)

    template_html = template_html_path.read_text(encoding="utf-8")
    
    # # richtextはHTMLとしてそのまま埋め込みたい

    body_html = fill_template(
        template_html=template_html,
        values=values,
        raw_fields=rich_field_names,
    )

    pprint("🪅🪅🪅:body_html")
    pprint(body_html)


    return body_html, all_segments
