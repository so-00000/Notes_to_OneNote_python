# main.py
from __future__ import annotations
import time
import re
import shutil
from pathlib import Path
from typing import Literal

import requests

try:
    import msvcrt  # Windows console key polling
except ImportError:  # pragma: no cover
    msvcrt = None

from .ignore_git import token
from .ignore_git.connection import GRAPH_ONENOTE_BASE_URL
from .config import NOTEBOOK_NAME, SLEEP_SEC
from .data_type_config import get_data_type_settings
from .find_id import find_notebook_id, find_section_id
from .models import AppSettings
from .services.graph_client import GraphClient
from .logging.logging_config import setup_logging
from .services.page_payload_builder import build_page_payload
from .services.migration_master_upsert import (
    build_source_id,
    delete_row_by_source_id,
    find_row_by_source_id,
    upsert_migration_master,
)

from scripts.delete_all_pages_in_section import delete_all_pages_in_section

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
        view_name=data_type_settings.view_name,
        dxl_dir=dxl_dir,
        sleep_sec=SLEEP_SEC,
    )


def _load_dxl_files(dxl_dir: Path) -> list[Path]:
    dxl_files = sorted(dxl_dir.glob("*.dxl"))
    if not dxl_files:
        raise RuntimeError(f"No DXL files found in: {dxl_dir}")
    return dxl_files


def _initial_link_resolution_status(payload) -> str:
    placeholders = payload.doclink_placeholders or []
    return "HAS_LINK_UNRESOLVED" if placeholders else "NO_LINK"


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


def _extract_first_url(text: str) -> str:
    m = re.search(r"https?://[^\s'\"<>]+", text or "")
    return m.group(0) if m else ""


def _extract_page_id_from_text(text: str) -> str:
    patterns = [
        r"/onenote/pages/([^/\s?]+)/content",
        r"/onenote/pages/([^/\s?]+)",
        r"[?&]page-id=([^&#\s]+)",
        r"[?&]pageid=([^&#\s]+)",
    ]
    for p in patterns:
        m = re.search(p, text or "")
        if m:
            page_id = m.group(1).strip("{}")
            page_id = page_id.replace("%7B", "").replace("%7D", "")
            return page_id
    return ""


def _resolve_existing_page_id(existing_row: dict[str, str]) -> str:
    # Graph API for /onenote/pages/{id} expects the Graph page id (e.g. 1-...!...)
    graph_page_id = (existing_row.get("onenote_page_id", "") or "").strip()
    if graph_page_id:
        return graph_page_id

    # Fallback: only parse page id from Graph endpoint-like error URLs.
    # Do not use client_url page-id (GUID), because it is not valid for this endpoint.
    for c in (
        existing_row.get("url_from_error", ""),
        existing_row.get("onenote_web_url", ""),
    ):
        pid = _extract_page_id_from_text(c)
        if pid and ("!" in pid or pid.startswith("1-")):
            return pid
    return ""


def _check_existing_page_state(
    client: GraphClient,
    existing_row: dict[str, str],
) -> Literal["exists", "not_found", "unknown"]:
    page_id = _resolve_existing_page_id(existing_row)
    if not page_id:
        return "unknown"

    try:
        client.get_onenote_page_content(page_id)
        return "exists"
    except requests.exceptions.Timeout:
        return "unknown"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 404:
            return "not_found"
        if status in {500, 502, 503, 504}:
            return "unknown"
        return "unknown"
    except RuntimeError:
        # GraphClient retries 500系の後に RuntimeError を投げるため Unknown 扱い
        return "unknown"
    except Exception:
        return "unknown"


def main() -> None:
    setup_logging(level="DEBUG")

    settings = _load_settings()
    dxl_files = _load_dxl_files(settings.dxl_dir)
    client = GraphClient(settings.access_token)
    cancel_monitor = EscCancellationMonitor(check_interval_sec=2.0)

    created = 0
    deleted_update_failed = 0
    duplicate_skipped_source_ids: list[str] = []
    duplicate_unknown_source_ids: list[str] = []
    mapping_path = Path(__file__).resolve().parent / "resources" / "mapping" / settings.view_name / "mapping.json"
    migration_master_csv = Path(__file__).resolve().parent / "doc_mapping" / settings.view_name / "migration_master.csv"
    update_failed_cleanup_targets: list[dict[str, str]] = []

    try:

        # 
        #　NotebookID
        # 

        # notebook_id = find_notebook_id(client, settings.notebook_name)


        # "本番：2_障害DB"
        notebook_id = "1-f120b7bd-5aca-447d-a23e-404d907cd6ec"


        # # "本番：3_データ強制変更"
        # notebook_id = "1-1fc57471-edb0-4751-a4ff-e8356669cef5"

        # "本番：5_UserCall"
        # notebook_id = "1-63307941-46a9-475f-8d12-9e4750b7f1e0"




        # 
        #　SectionID
        # 

        # section_id = find_section_id(client, notebook_id, settings.section_name)

        section_name = "障害DB_2024"
        section_id = find_section_id(client, notebook_id, section_name)


        delete_flg = False


        if delete_flg:
            delete_all_pages_in_section(client, section_id)
        else:
            print("[INFO] Press Esc to request cancellation (stops at next safe check).")
            for i, dxl_path in enumerate(dxl_files, start=1):
                payload = None
                try:
                    cancel_monitor.check()

                    payload = build_page_payload(
                        dxl_path,
                        row_no=i,
                    )

                    source_id = build_source_id(payload)
                    existing_row = find_row_by_source_id(migration_master_csv, source_id)
                    if existing_row:
                        existing_state = _check_existing_page_state(client, existing_row)
                        if existing_state == "exists":
                            if source_id:
                                duplicate_skipped_source_ids.append(source_id)
                            moved_path = _move_file_to_subdir(dxl_path, "duplicate")
                            print(f"[SKIP:duplicate] {dxl_path.name} source_id={source_id} -> {moved_path}")
                            continue
                        if existing_state == "unknown":
                            if source_id:
                                duplicate_unknown_source_ids.append(source_id)
                            moved_path = _move_file_to_subdir(dxl_path, "error")
                            print(
                                f"[SKIP:unknown] {dxl_path.name} "
                                f"source_id={source_id} -> {moved_path}"
                            )
                            continue
                        deleted = delete_row_by_source_id(
                            mapping_path=mapping_path,
                            csv_path=migration_master_csv,
                            source_id=source_id,
                        )
                        print(f"[INFO:recreate] stale source_id={source_id}, removed_rows={deleted}")

                    # 1) 新規作成
                    page, rest_segments = client.create_onenote_page_base(
                        section_id=section_id,
                        page_payload=payload,
                    )

                    page_id = page.get("id")
                    links = page.get("links") or {}
                    web_url = (links.get("oneNoteWebUrl") or {}).get("href") or ""
                    client_url = (links.get("oneNoteClientUrl") or {}).get("href") or ""

                    # 2) 作成後更新（残りセグメント）
                    try:
                        client.append_onenote_page_remaining_segments(
                            page_id=page_id,
                            segments=rest_segments,
                        )
                    except Exception as update_error:
                        update_error_message = str(update_error)
                        url_from_error = _extract_first_url(update_error_message)
                        if not url_from_error and page_id:
                            url_from_error = f"{GRAPH_ONENOTE_BASE_URL}/pages/{page_id}/content"

                        upsert_migration_master(
                            view_name=settings.view_name,
                            mapping_path=mapping_path,
                            csv_path=migration_master_csv,
                            payload=payload,
                            page_id=page_id or "",
                            web_url=web_url,
                            client_url=client_url,
                            url_from_error=url_from_error,
                            status="error:update_failed",
                            error_message=update_error_message,
                            link_resolution_status=_initial_link_resolution_status(payload),
                        )

                        update_failed_cleanup_targets.append(
                            {
                                "page_id": page_id or "",
                                "url_from_error": url_from_error,
                                "error_message": update_error_message,
                            }
                        )
                        moved_path = _move_file_to_subdir(dxl_path, "error")
                        print(f"[ERROR:update] {dxl_path.name}: {update_error} -> {moved_path}")
                        continue

                    created += 1

                    upsert_migration_master(
                        view_name=settings.view_name,
                        mapping_path=mapping_path,
                        csv_path=migration_master_csv,
                        payload=payload,
                        page_id=page_id or "",
                        web_url=web_url,
                        client_url=client_url,
                        status="done",
                        link_resolution_status=_initial_link_resolution_status(payload),
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
                    if payload is not None:
                        error_message = str(e)
                        url_from_error = _extract_first_url(error_message)
                        upsert_migration_master(
                            view_name=settings.view_name,
                            mapping_path=mapping_path,
                            csv_path=migration_master_csv,
                            payload=payload,
                            url_from_error=url_from_error,
                            status="error:create_failed",
                            error_message=error_message,
                            link_resolution_status=_initial_link_resolution_status(payload),
                        )
                    moved_path = _move_file_to_subdir(dxl_path, "error")
                    print(f"[ERROR] {dxl_path.name}: {e} -> {moved_path}")

            # ② update_failed のみ後処理で削除
            deleted_ids: set[str] = set()
            for target in update_failed_cleanup_targets:
                page_id = (target.get("page_id") or "").strip()
                if not page_id:
                    page_id = _extract_page_id_from_text(target.get("url_from_error", ""))
                if not page_id:
                    page_id = _extract_page_id_from_text(target.get("error_message", ""))
                if not page_id or page_id in deleted_ids:
                    continue
                try:
                    client.delete_onenote_page(page_id=page_id)
                    deleted_ids.add(page_id)
                    deleted_update_failed += 1
                except Exception as delete_error:
                    print(f"[WARN:cleanup] page_id={page_id} delete failed: {delete_error}")

            if duplicate_skipped_source_ids:
                joined = ", ".join(duplicate_skipped_source_ids)
                print(f"[DUPLICATE] skipped source_id: {joined}")
            if duplicate_unknown_source_ids:
                joined_unknown = ", ".join(duplicate_unknown_source_ids)
                print(f"[DUPLICATE] unknown-check source_id (not recreated): {joined_unknown}")
            print(
                "✅  Done. \r\n"
                f"✅  Created pages: {created}, \r\n"
                f"✅  cleaned update-failed pages: {deleted_update_failed}, \r\n"
                f"✅  duplicate skipped: {len(duplicate_skipped_source_ids)}, \r\n"
                f"✅  duplicate unknown: {len(duplicate_unknown_source_ids)}"
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
