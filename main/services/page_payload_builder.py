# page_payload_builder.py
from __future__ import annotations
from pathlib import Path
from main.services.dxl_to_page_material import create_materials_from_dxl
from main.services.renderer import render_to_html_body
from main.models.models import PagePayload


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
    
    # 各コンテンツデータの抽出（各項目/値・セグメントデータ（バイナリデータ・位置情報）など）
    note, segment_list = create_materials_from_dxl(str(dxl_path))

    # ページタイトル作成（ドキュメント番号_件名）
    # 障害DB用
    # page_title = note.DocumentNo + "_" + note.Fd_Text_1

    # CallDB用
    page_title = note.mng_no + "_" + note.outline

    # 本文作成（HTML）
    body_html = render_to_html_body(note, source_file=base, row_no=row_no)


    return PagePayload(
        page_title = page_title,
        body_html =  body_html,
        segment_list =  segment_list,
    )
