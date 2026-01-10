# main.py
from __future__ import annotations

import os
import time
from pathlib import Path
from dataclasses import dataclass

from .ignore_git import token
from .config import (
    NOTEBOOK_NAME,
    SECTION_NAME,
    DXL_DIR,
    TITLE_COLUMN,
    SLEEP_SEC,
)
from .find_id import find_notebook_id, find_section_id
from .graph_client import GraphClient
from .renderer_rich import render_incident_like_page
from .dxl_to_payload import dxl_to_onenote_payload, BinaryPart
from .delete_all_pages_in_section import delete_all_pages_in_section

@dataclass(frozen=True)
class AppSettings:
    """アプリ全体で使う設定値をひとまとめにする。"""

    access_token: str
    notebook_name: str
    section_name: str
    dxl_dir: Path
    title_column: str | None
    sleep_sec: float
    rich_fields: list[str]


def _make_title(note: object, dxl_filename: str, *, title_column: str | None) -> str:
    """
    タイトルの決定ルール。

    1. config.TITLE_COLUMN があればその値を優先
    2. DocumentNo/DetailSubject/ReasonSubject を順に探す
    3. それも無い場合はファイル名
    """
    if title_column:
        v = getattr(note, title_column, None)
        if v and str(v).strip():
            return str(v).strip()

    for key in ("DocumentNo", "DetailSubject", "ReasonSubject"):
        v = getattr(note, key, None)
        if v and str(v).strip():
            return str(v).strip()

    return dxl_filename


def _resolve_dxl_dir(config_value: str) -> Path:
    """DXL_DIRの相対/絶対を正規化してPathにする。"""
    if not config_value or not str(config_value).strip():
        raise RuntimeError("DXL_DIR is empty. Set it in config.py")

    dxl_path = Path(config_value)
    if dxl_path.is_absolute():
        return dxl_path

    base_dir = Path(__file__).resolve().parent
    return (base_dir / dxl_path).resolve()


def _validate_config() -> None:
    """必須設定のバリデーション。"""
    if not NOTEBOOK_NAME or not str(NOTEBOOK_NAME).strip():
        raise RuntimeError("NOTEBOOK_NAME is empty. Set it in config.py")
    if not SECTION_NAME or not str(SECTION_NAME).strip():
        raise RuntimeError("SECTION_NAME is empty. Set it in config.py")


def _load_settings() -> AppSettings:
    """config.pyとtokenからAppSettingsを組み立てる。"""
    access_token = token.ACCESS_TOKEN
    if not access_token or not access_token.strip():
        raise RuntimeError("ACCESS_TOKEN is empty.")

    _validate_config()

    dxl_dir = _resolve_dxl_dir(DXL_DIR)
    if not dxl_dir.exists():
        raise RuntimeError(f"DXL_DIR not found: {dxl_dir}")
    if not dxl_dir.is_dir():
        raise RuntimeError(f"DXL_DIR is not a directory: {dxl_dir}")

    # 画像（スクショ）を拾う可能性のあるRichTextフィールド
    rich_fields = ["Detail", "Reason", "Temporary", "Parmanent"]

    return AppSettings(
        access_token=access_token,
        notebook_name=NOTEBOOK_NAME,
        section_name=SECTION_NAME,
        dxl_dir=dxl_dir,
        title_column=TITLE_COLUMN or None,
        sleep_sec=SLEEP_SEC,
        rich_fields=rich_fields,
    )


def _load_dxl_files(dxl_dir: Path) -> list[Path]:
    """指定ディレクトリ内のDXLファイル一覧を取得する。"""
    dxl_files = sorted(dxl_dir.glob("*.dxl"))
    if not dxl_files:
        raise RuntimeError(f"No DXL files found in: {dxl_dir}")
    return dxl_files


def _build_page_payload(
    dxl_path: Path,
    *,
    row_no: int,
    title_column: str | None,
    rich_fields: list[str],
) -> tuple[str, str, list[BinaryPart]]:
    """
    DXL1件を読み込み、OneNoteへ送るための情報を作る。

    戻り値: (title, body_html, image_parts)
    """
    base = os.path.basename(str(dxl_path))
    note, parts = dxl_to_onenote_payload(str(dxl_path), rich_fields=rich_fields)
    title = _make_title(note, base, title_column=title_column)
    body_html = render_incident_like_page(note, source_file=base, row_no=row_no)
    return title, body_html, parts


def main() -> None:
    settings = _load_settings()

    dxl_files = _load_dxl_files(settings.dxl_dir)

    client = GraphClient(settings.access_token)

    # # 削除したいとき
    # notebook_id = find_notebook_id(client, settings.notebook_name)
    # section_id = find_section_id(client, notebook_id, settings.section_name)
    # delete_all_pages_in_section(client, section_id)

    # #########################################################

    created = 0

    try:
        notebook_id = find_notebook_id(client, settings.notebook_name)
        section_id = find_section_id(client, notebook_id, settings.section_name)

        for i, dxl_path in enumerate(dxl_files, start=1):
            title, body_html, parts = _build_page_payload(
                dxl_path,
                row_no=i,
                title_column=settings.title_column,
                rich_fields=settings.rich_fields,
            )

            page = client.create_onenote_page(
                section_id=section_id,
                page_title=title,
                body_html=body_html,
                parts=parts,
            )

            web_url = (page.get("links", {}).get("oneNoteWebUrl", {}) or {}).get("href")
            created += 1

            img_count = sum(1 for p in parts if p.content_type.startswith("image/"))
            att_count = len(parts) - img_count
            print(f"[OK] {created}: title='{title}' images={img_count} attachments={att_count} url={web_url}")


            if settings.sleep_sec:
                time.sleep(settings.sleep_sec)

        print(f"Done. Created pages: {created}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
