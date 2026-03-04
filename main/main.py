# main.py
from __future__ import annotations
import time
import json
import shutil
from pathlib import Path
from dataclasses import dataclass, asdict

try:
    import msvcrt  # Windows console key polling
except ImportError:  # pragma: no cover
    msvcrt = None

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
    access_token: str
    notebook_name: str
    section_name: str
    dxl_dir: Path
    sleep_sec: float


class UserCancelledError(Exception):
    """Raised when user requests cancellation via Esc key."""


class EscCancellationMonitor:
    """
    Lightweight Esc-key monitor.
    Checks at a coarse interval to minimize impact on main processing.
    """

    def __init__(self, check_interval_sec: float = 2.0) -> None:
        self._check_interval_sec = check_interval_sec
        self._next_check_at = time.monotonic()

    def check(self) -> None:
        if msvcrt is None:
            return

        now = time.monotonic()
        if now < self._next_check_at:
            return
        self._next_check_at = now + self._check_interval_sec

        while msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x1b":
                raise UserCancelledError("Esc key pressed.")
            # Special keys can start with \x00/\xe0 and include a second code.
            if ch in ("\x00", "\xe0") and msvcrt.kbhit():
                _ = msvcrt.getwch()


def _resolve_dxl_dir(config_value: str) -> Path:
    if not config_value or not str(config_value).strip():
        raise RuntimeError("DXL_DIR is empty. Set it in config.py")

    dxl_path = Path(config_value)
    if dxl_path.is_absolute():
        return dxl_path

    base_dir = Path(__file__).resolve().parent
    return (base_dir / dxl_path).resolve()


def _validate_config() -> None:
    if not NOTEBOOK_NAME or not str(NOTEBOOK_NAME).strip():
        raise RuntimeError("NOTEBOOK_NAME is empty. Set it in config.py")
    get_data_type_settings()


def _load_settings() -> AppSettings:
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
    dxl_files = sorted(dxl_dir.glob("*.dxl"))
    if not dxl_files:
        raise RuntimeError(f"No DXL files found in: {dxl_dir}")
    return dxl_files


def _build_unique_destination(path: Path) -> Path:
    """Avoid overwrite: append suffix when destination already exists."""
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


def _move_file_to_subdir(src: Path, subdir_name: str) -> Path:
    """Move one source file into src.parent/subdir_name."""
    target_dir = src.parent / subdir_name
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = _build_unique_destination(target_dir / src.name)
    shutil.move(str(src), str(dest))
    return dest


def main() -> None:
    setup_logging(level="DEBUG")

    settings = _load_settings()
    dxl_files = _load_dxl_files(settings.dxl_dir)
    client = GraphClient(settings.access_token)
    cancel_monitor = EscCancellationMonitor(check_interval_sec=2.0)

    created = 0
    link_log: dict[str, object] = {"pages": []}
    link_log_path = Path(__file__).resolve().parents[1] / "logs" / "onenote_link_map.json"

    try:

        # 
        #　NotebookID
        # 

        # notebook_id = find_notebook_id(client, settings.notebook_name)

        #小石沢さんノート
        # notebook_id = "1-f4f7d836-51c5-405d-8aff-7e81033a27ed"



        # "本番：データ強制変更"
        notebook_id = "1-1fc57471-edb0-4751-a4ff-e8356669cef5"

        # # "本番：2_障害DB"
        # notebook_id = "1-f120b7bd-5aca-447d-a23e-404d907cd6ec"




        # 
        #　SectionID
        # 

        section_name = "データ強制変更"
        section_id = find_section_id(client, notebook_id, section_name)
        # section_id = find_section_id(client, notebook_id, settings.section_name)


        #小石沢さんセクション
        # section_id = "1-113c71a1-51a5-48c0-94db-64d2982dcb5a"

        # "本番：2_障害DB"
        # section_id = "1-4cf9ae1f-1aef-4113-a50e-be6ecc1895c1"
        # section_id = "1-967f1cfa-8195-4672-bb4f-407c21e67cd1"

        # 障害DB_2024
        # section_id = "1-5f4aa77a-607b-4740-8d34-ebf84aed8dbc"

        # # 障害DB_2023
        # section_id = "1-96e3fc6b-abe5-4901-ba88-f4f60ca9aba3"

        # # 障害DB_2022
        # section_id = "1-c9cb3445-0f8f-4c60-9cd1-8e24ea5bc42d"

        # # 障害DB_2021
        # section_id = "1-02d62dcd-ba0d-4926-9b2a-c3f37e265893"

        # 障害DB_2020
        # section_id = "1-2552d78c-8f74-4551-82ad-ea771cda7ba5"

        # # 障害DB_2019
        # section_id = "1-3376de02-f2a9-40c3-a2f2-3e80ea2f5fe3"

        # # 障害DB_2018
        # section_id = "1-66c4b5d7-80c9-40ce-8599-6bb712065b04"

        # # 障害DB_2017
        # section_id = "1-aabb7743-c438-4704-8140-f879e6af1755"

        # 障害DB_2016
        # section_id = "1-a4f43d0f-df72-4348-bffd-ecdcbece0fc2"

        # "本番：データ強制変更"
        # section_id = "1-05c3903a-d2c0-4acf-8140-9ff748e1fc05"



        delete_flg = False

        if delete_flg:
            delete_all_pages_in_section(client, section_id)
        else:
            print("[INFO] Press Esc to request cancellation (stops at next safe check).")
            for i, dxl_path in enumerate(dxl_files, start=1):
                try:
                    cancel_monitor.check()

                    payload = build_page_payload(
                        dxl_path,
                        row_no=i,
                    )

                    page = client.create_onenote_page(
                        section_id=section_id,
                        page_payload=payload,
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

                    moved_path = _move_file_to_subdir(dxl_path, "complete")
                    print(f"[OK] {dxl_path.name} -> {moved_path}")

                    if settings.sleep_sec:
                        time.sleep(settings.sleep_sec)
                        cancel_monitor.check()
                except UserCancelledError:
                    print(f"[CANCELLED] Stopped by Esc. Created pages: {created}")
                    break
                except Exception as e:
                    moved_path = _move_file_to_subdir(dxl_path, "error")
                    print(f"[ERROR] {dxl_path.name}: {e} -> {moved_path}")

            # if link_log["pages"]:
            #     link_log_path.parent.mkdir(parents=True, exist_ok=True)
            #     link_log_path.write_text(
            #         json.dumps(link_log, ensure_ascii=True, indent=2),
            #         encoding="utf-8",
            #     )

            print(f"🪅Done. Created pages: {created}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
