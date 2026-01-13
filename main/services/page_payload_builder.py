# page_payload_builder.py
from __future__ import annotations
from pathlib import Path
from main.data_type_config import get_data_type_settings
from main.services.dxl_to_page_material import create_materials_from_dxl
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
    
    data_type = get_data_type_settings()

    # 各コンテンツデータの抽出（各項目/値・セグメントデータ（バイナリデータ・位置情報）など）
    note, segment_list = create_materials_from_dxl(str(dxl_path))

    # ページタイトル作成（指定フィールドを結合）
    title_parts = []
    for field_name in data_type.title_fields:
        value = getattr(note, field_name, None)
        if value:
            title_parts.append(str(value))
    page_title = "_".join(title_parts) if title_parts else base

    # 本文作成（HTML）
    body_html = data_type.renderer(note, source_file=base, row_no=row_no)


    return PagePayload(
        page_title = page_title,
        body_html =  body_html,
        segment_list =  segment_list,
    )
