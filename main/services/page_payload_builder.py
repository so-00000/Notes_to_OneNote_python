# page_payload_builder.py
from __future__ import annotations
import json
import html
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from main import config
from main.data_type_config import get_data_type_settings
from main.enums import DataType
from main.services.dxl_to_ui_field_map import dxl_to_field_map, dxl_to_ui_field_map
from main.services.render_body_html_and_segments import render_body_html_and_segments
from main.models.models import PagePayload
from main.services.load_field import load_visible_field_names, load_richtext_field_names
from main.services.onenote_limits import MAX_GRAPH_MULTIPART_PART_BYTES

from pprint import pprint


DXL_NS = {"dxl": "http://www.lotus.com/dxl"}
logger = logging.getLogger(__name__)
_FORMULA_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_LOTUS_FORMULA_RESERVED_WORDS = {
    "Text",
    "Right",
    "If",
}
_CALL2024_TWO_DIGIT_DATETIME_FIELDS = {
    "ADATE_D_2",
    "ADATE_M_2",
    "ATIME_H_2",
    "ATIME_M_2",
    "CDATE_D_2",
    "CDATE_M_2",
    "CTIME_H_2",
    "CTIME_M_2",
    "EDATE_D_2",
    "EDATE_D",
    "EDATE_M_2",
    "EDATE_M",
    "ESDATE_D_1",
    "ESDATE_M_1",
    "ESTIME_H_1",
    "ESTIME_M_1",
    "ETIME_H_2",
    "ETIME_H",
    "ETIME_M_2",
    "ETIME_M",
    "JDATE_D",
    "JDATE_M",
    "JTIME_H",
    "JTIME_M",
    "PCDY",
    "PCMY",
    "SDATE_D_2",
    "SDATE_D",
    "SDATE_M_2",
    "SDATE_M",
    "STIME_H_2",
    "STIME_H",
    "STIME_M_2",
    "STIME_M",
    "TDATE_D",
    "TDATE_M",
    "TTIME_H",
    "TTIME_M",
}


def _resolve_path(value: str | Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / p).resolve()


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]', "_", (value or "").strip())
    sanitized = sanitized.rstrip(" .")
    return sanitized or "attachment.bin"


def _build_unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        candidate = path.parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _replace_segment_anchor_with_notice(body_html: str, segment_id: str, notice_html: str) -> str:
    sid = re.escape(segment_id)
    pattern = re.compile(
        rf"<div\b[^>]*\bdata-id=['\"]{sid}['\"][^>]*>.*?</div>",
        re.IGNORECASE | re.DOTALL,
    )
    replaced_html, replace_count = pattern.subn(notice_html, body_html, count=1)
    if replace_count == 0:
        logger.warning("oversize segment anchor not found in body_html: %s", segment_id)
    return replaced_html


def _notice_html_for_exported_binary(*, filename: str, relative_path: Path, size_bytes: int) -> str:
    escaped_filename = html.escape(filename)
    escaped_path = html.escape(relative_path.as_posix())
    return (
        "<div style='margin:8px 0; padding:10px; border:1px dashed #c58f00; "
        "border-radius:10px; background:#fff8e1; color:#5f4300;'>"
        f"添付ファイル: {escaped_filename}<br/>"
        f"サイズ超過のため別出力: {escaped_path}<br/>"
        f"ファイルサイズ: {size_bytes} bytes"
        "</div>"
    )


def _export_oversize_segments(
    *,
    dxl_path: Path,
    body_html: str,
    segment_list: list,
) -> tuple[str, list]:
    kept_segments = []
    updated_body_html = body_html
    export_dir = dxl_path.parent.parent / "result" / "oversize_attachments" / dxl_path.parent.name / dxl_path.stem

    for seg in segment_list:
        size_bytes = len(seg.binary_part.data)
        if size_bytes <= MAX_GRAPH_MULTIPART_PART_BYTES:
            kept_segments.append(seg)
            continue

        export_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = _sanitize_filename(seg.binary_part.filename)
        exported_path = _build_unique_destination(export_dir / safe_filename)
        exported_path.write_bytes(seg.binary_part.data)

        relative_path = exported_path.relative_to(dxl_path.parent.parent)
        notice_html = _notice_html_for_exported_binary(
            filename=exported_path.name,
            relative_path=relative_path,
            size_bytes=size_bytes,
        )
        updated_body_html = _replace_segment_anchor_with_notice(
            updated_body_html,
            seg.segment_id,
            notice_html,
        )
        logger.warning(
            "exported oversize binary instead of embedding: dxl=%s segment=%s filename=%s size=%s path=%s",
            dxl_path.name,
            seg.segment_id,
            seg.binary_part.filename,
            size_bytes,
            exported_path,
        )

    return updated_body_html, kept_segments


def _load_migration_master_field_names(view_name: str) -> set[str]:
    mapping_path = _resolve_path(Path("resources") / "mapping" / view_name / "mapping.json")
    data = json.loads(mapping_path.read_text(encoding="utf-8"))

    field_names: set[str] = set()
    for view in data.get("views", {}).values():
        for col in view.get("view_columns", []):
            item_name = str(col.get("item_name") or "").strip()
            if item_name:
                field_names.add(item_name)
            formula = str(col.get("formula") or "").strip()
            if formula:
                for token in _FORMULA_IDENTIFIER_RE.findall(formula):
                    if token not in _LOTUS_FORMULA_RESERVED_WORDS:
                        field_names.add(token)
    return field_names


def _zero_pad_two_digit_datetime_part(value: str) -> str:
    s = str(value).strip()
    if not s:
        return s
    if not re.fullmatch(r"\d{1,2}", s):
        return s
    return s.zfill(2)


def _normalize_call2024_datetime_parts(ui_field_map: dict[str, str]) -> dict[str, str]:
    normalized = dict(ui_field_map)
    for field_name in _CALL2024_TWO_DIGIT_DATETIME_FIELDS:
        if field_name not in normalized:
            continue
        normalized[field_name] = _zero_pad_two_digit_datetime_part(normalized[field_name])
    return normalized


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
    if config.DATA_TYPE == DataType.CALL2024:
        ui_field_map = _normalize_call2024_datetime_parts(ui_field_map)
    migration_master_field_names = _load_migration_master_field_names(data_type.view_name)
    migration_master_map = dxl_to_field_map(
        root=root,
        target_field_names=migration_master_field_names,
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
    body_html, segment_list = _export_oversize_segments(
        dxl_path=dxl_path,
        body_html=body_html,
        segment_list=segment_list,
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
        migration_master_map = migration_master_map,
        doclink_placeholders = doclink_placeholders,
    )

    # pprint(pagePayload)


    return pagePayload
