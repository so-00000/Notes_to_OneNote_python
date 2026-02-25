# main.py
from __future__ import annotations
import time
import json
from pathlib import Path
from dataclasses import dataclass, asdict

from .ignore_git import token
from .config import NOTEBOOK_NAME, SLEEP_SEC
from .data_type_config import get_data_type_settings
from .find_id import find_notebook_id, find_section_id
from .services.graph_client import GraphClient
from .logging.logging_config import setup_logging
from .services.page_payload_builder import build_page_payload

from .delete_all_pages_in_section import delete_all_pages_in_section




@dataclass(frozen=True)
class AppSettings:
    """アプリ全体で使う設定値"""
    access_token: str
    notebook_name: str
    section_name: str
    dxl_dir: Path
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
    get_data_type_settings()


def _load_settings() -> AppSettings:
    """config.pyとtokenからAppSettingsを組み立てる。"""
    access_token = token.ACCESS_TOKEN
    if not access_token or not access_token.strip():
        raise RuntimeError("ACCESS_TOKEN is empty.")

    _validate_config()

    data_type_settings = get_data_type_settings()
    dxl_dir = _resolve_dxl_dir(data_type_settings.dxl_dir)
    if not dxl_dir.exists():
        raise RuntimeError(f"DXL_DIR not found: {dxl_dir}")
    if not dxl_dir.is_dir():
        raise RuntimeError(f"DXL_DIR is not a directory: {dxl_dir}")

    return AppSettings(
        access_token=access_token,
        notebook_name=NOTEBOOK_NAME,
        section_name=data_type_settings.section_name,
        dxl_dir=dxl_dir,
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
    link_log: dict[str, object] = {"pages": []}
    link_log_path = Path(__file__).resolve().parents[1] / "logs" / "onenote_link_map.json"

    try:
        # # 対象OneNoteのノートブックID・セクションIDの取得
        notebook_id = find_notebook_id(client, settings.notebook_name)
        section_id = find_section_id(client, notebook_id, settings.section_name)


        delete_flg = False

        # 削除したいとき
        if delete_flg:
            delete_all_pages_in_section(client, section_id)

        else:
                # DXLファイルを1件ずつ処理
            for i, dxl_path in enumerate(
                dxl_files,
                start=1
                ):

                # タイトル・本文・画像/添付ファイルの作成
                payload = build_page_payload(
                    dxl_path,
                    row_no=i,
                )
                
                # OneNoteページ作成のリクエスト
                page = client.create_onenote_page(
                    section_id=section_id,
                    page_payload=payload
                )

                created += 1

                page_id = page.get("id")
                links = page.get("links") or {}
                web_url = (links.get("oneNoteWebUrl") or {}).get("href") or ""
                client_url = (links.get("oneNoteClientUrl") or {}).get("href") or ""

                doc_key = None
                if payload.doc_replicaid and payload.doc_unid:
                    doc_key = f"{payload.doc_replicaid}:{payload.doc_unid}"

                link_log["pages"].append(
                    {
                        "doc_key": doc_key,
                        "page_id": page_id,
                        "web_url": web_url,
                        "client_url": client_url,
                        "placeholders": [asdict(p) for p in payload.doclink_placeholders],
                    }
                )

                if settings.sleep_sec:
                    time.sleep(settings.sleep_sec)

            # if link_log["pages"]:
            #     link_log_path.parent.mkdir(parents=True, exist_ok=True)
            #     link_log_path.write_text(
            #         json.dumps(link_log, ensure_ascii=True, indent=2),
            #         encoding="utf-8",
            #     )

            print(f"Done. Created pages: {created}")

    finally:
        client.close()

if __name__ == "__main__":
    main()