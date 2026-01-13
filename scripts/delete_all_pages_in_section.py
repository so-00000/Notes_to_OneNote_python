# main.py
from __future__ import annotations
from dataclasses import dataclass

from .ignore_git import token
from .config import NOTEBOOK_NAME
from .data_type_config import get_data_type_settings
from .find_id import find_notebook_id, find_section_id
from .services.graph_client import GraphClient
from .logging.logging_config import setup_logging
from .delete_all_pages_in_section import delete_all_pages_in_section

@dataclass(frozen=True)
class AppSettings:
    """アプリ全体で使う設定値"""
    access_token: str
    notebook_name: str
    section_name: str


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


    return AppSettings(
        access_token=access_token,
        notebook_name=NOTEBOOK_NAME,
        section_name=get_data_type_settings().section_name,
    )





def main() -> None:

    setup_logging(level="DEBUG")
    
    settings = _load_settings()
    client = GraphClient(settings.access_token)

    # 対象OneNoteのノートブックID・セクションIDの取得
    notebook_id = find_notebook_id(client, settings.notebook_name)
    section_id = find_section_id(client, notebook_id, settings.section_name)
    delete_all_pages_in_section(client, section_id)

    client.close()


if __name__ == "__main__":
    main()
