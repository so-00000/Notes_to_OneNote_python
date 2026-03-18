# page_payload_builder.py
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from main.data_type_config import get_data_type_settings
from main.services.dxl_to_ui_field_map import dxl_to_ui_field_map
from main.services.render_body_html_and_segments import render_body_html_and_segments
from main.models.models import PagePayload
from main.services.load_field import load_visible_field_names, load_richtext_field_names

from pprint import pprint


DXL_NS = {"dxl": "http://www.lotus.com/dxl"}


def _resolve_path(value: str | Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / p).resolve()


def build_page_payload(
    dxl_path: Path,
    *,
    row_no: int,
) -> PagePayload:
    """
    DXL1件を読み込み、OneNoteへ送るための情報を作る。

    戻り値: PagePayload
    """
    base = dxl_path.name

    data_type = get_data_type_settings()

    # DXLファイルの解析（XMLツリーに変換後、ツリーのルート要素を取得）
    root = ET.parse(dxl_path).getroot()
    doc_replicaid = root.get("replicaid")
    noteinfo = root.find("dxl:noteinfo", DXL_NS)
    doc_unid = noteinfo.get("unid") if noteinfo is not None else None

    fields_json_path = _resolve_path(data_type.fields_json_path)


    # 表示する画面項目を取得
    visible_field_names = load_visible_field_names(fields_json_path)
    # RichTextの画面項目を取得
    richtext_field_names = load_richtext_field_names(fields_json_path)


    # 画面表示する項目を辞書型で取得（※RichTextフィールド除外）
    ui_field_map = dxl_to_ui_field_map(
        root = root,
        visible_field_names = visible_field_names,
        richtext_field_names = richtext_field_names,
        )

    # pprint("🪅🪅🪅：ui_field_map")
    # pprint(ui_field_map)
    

    # ページタイトル作成
    v = ui_field_map.get(data_type.title_field)
    page_title = str(v).strip() if v is not None else ""
    if not page_title:
        page_title = base

    # pprint("🪅🪅🪅：page_title")
    # pprint(page_title)
    

    # HTML・セグメントデータ（バイナリデータ・位置情報）など）
    body_html, segment_list, doclink_placeholders = render_body_html_and_segments(
        root=root,
        ui_field_map=ui_field_map,
        data_type=data_type,
        rich_field_names=richtext_field_names,
    )

    # pprint("🪅🪅🪅：body_html")
    # pprint(body_html)

    # pprint("🪅🪅🪅：segment_list")
    # pprint(segment_list)

    pagePayload = PagePayload(
        page_title = page_title,
        body_html =  body_html,
        segment_list =  segment_list,
        doc_replicaid = doc_replicaid,
        doc_unid = doc_unid,
        extracted_fields = dict(ui_field_map),
        doclink_placeholders = doclink_placeholders,
    )

    # pprint(pagePayload)


    return pagePayload
