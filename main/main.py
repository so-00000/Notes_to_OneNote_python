# main.py
from __future__ import annotations
import time
from pathlib import Path
from dataclasses import dataclass

from main.ignore_git import token
from main.config import (
    NOTEBOOK_NAME,
    SECTION_NAME,
    DXL_DIR,
    TITLE_COLUMN,
    SLEEP_SEC,
)
from main.find_id import find_notebook_id, find_section_id
from main.services.graph_client import GraphClient
from main.logging.logging_config import setup_logging
from main.services.page_payload_builder import build_page_payload



@dataclass(frozen=True)
class AppSettings:
    """アプリ全体で使う設定値"""
    access_token: str
    notebook_name: str
    section_name: str
    dxl_dir: Path
    title_column: str | None
    sleep_sec: float





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

    return AppSettings(
        access_token=access_token,
        notebook_name=NOTEBOOK_NAME,
        section_name=SECTION_NAME,
        dxl_dir=dxl_dir,
        title_column=TITLE_COLUMN or None,
        sleep_sec=SLEEP_SEC,
    )


def _load_dxl_files(dxl_dir: Path) -> list[Path]:
    """指定ディレクトリ内のDXLファイル一覧を取得する。"""
    dxl_files = sorted(dxl_dir.glob("*.dxl"))
    if not dxl_files:
        raise RuntimeError(f"No DXL files found in: {dxl_dir}")
    return dxl_files



def main() -> None:

    setup_logging(level="DEBUG")
    
    settings = _load_settings()
    dxl_files = _load_dxl_files(settings.dxl_dir)
    client = GraphClient(settings.access_token)

    created = 0

    try:
        # 対象OneNoteのノートブックID・セクションIDの取得
        notebook_id = find_notebook_id(client, settings.notebook_name)
        section_id = find_section_id(client, notebook_id, settings.section_name)


        # DXLファイルを1件ずつ処理
        for i, dxl_path in enumerate(dxl_files, start=1):

            # タイトル・本文・画像/添付ファイルの作成
            payload = build_page_payload(
                dxl_path,
                row_no=i,
            )


            # OneNoteページ作成のリクエスト
            client.create_onenote_page(
                section_id=section_id,
                page_payload=payload
            )

            created += 1


            if settings.sleep_sec:
                time.sleep(settings.sleep_sec)

        print(f"Done. Created pages: {created}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
