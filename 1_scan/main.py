# main.py
from __future__ import annotations

import html
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests

from config import (
    ACCESS_TOKEN,
    NOTEBOOK_NAME,
    SECTION_NAME,
    DXL_DIR,
    TITLE_COLUMN,
    SLEEP_SEC,
)
from find_id import find_notebook_id, find_section_id
from renderer_rich import render_incident_like_page

# ★ 追加：DXL -> (OneNoteRow, parts)
from dxl_to_payload import dxl_to_onenote_payload, BinaryPart


# ========= OneNote POST (multipart) =========

def _post_onenote_page_multipart(
    session: requests.Session,
    access_token: str,
    section_id: str,
    page_title: str,
    body_html: str,
    parts: list[BinaryPart],
) -> dict:
    url = f"https://graph.microsoft.com/v1.0/me/onenote/sections/{quote(section_id)}/pages"

    xhtml = f"""<!DOCTYPE html>
<html>
  <head>
    <title>{html.escape(page_title)}</title>
  </head>
  <body>
{body_html}
  </body>
</html>"""

    headers = {
        "Authorization": f"Bearer {access_token}",
        # ★ Content-Type は付けない（requestsがboundary付きで付ける）
    }

    # ★ Graph制約対策：Presentation含め最大6パート → 画像は最大5
    if len(parts) > 5:
        parts = parts[:5]

    files = {
        "Presentation": ("presentation.html", xhtml, "text/html"),
    }
    for p in parts:
        # <img src="name:{p.name}"> と一致するキーで送る
        files[p.name] = (p.filename, p.data, p.content_type)

    for _ in range(5):
        r = session.post(url, headers=headers, files=files)

        if r.status_code in (429, 503):
            wait = int(r.headers.get("Retry-After", "2"))
            time.sleep(wait)
            continue

        if r.status_code == 401:
            raise RuntimeError(
                "401 Unauthorized. Access token expired/invalid. "
                "Update ACCESS_TOKEN and retry."
            )

        r.raise_for_status()
        return r.json()

    raise RuntimeError("Failed to create page after retries (429/503).")


# ========= helpers =========

def _make_title(note, dxl_filename: str) -> str:
    if TITLE_COLUMN:
        v = getattr(note, TITLE_COLUMN, None)
        if v and str(v).strip():
            return str(v).strip()

    for key in ("DocumentNo", "DetailSubject", "ReasonSubject"):
        v = getattr(note, key, None)
        if v and str(v).strip():
            return str(v).strip()

    return dxl_filename


# ======== (delete util はそのまま残してOK) ========

def _graph_get(session: requests.Session, access_token: str, url: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    for _ in range(5):
        r = session.get(url, headers=headers)
        if r.status_code in (429, 503):
            wait = int(r.headers.get("Retry-After", "2"))
            time.sleep(wait)
            continue
        if r.status_code == 401:
            raise RuntimeError("401 Unauthorized. Access token expired/invalid.")
        r.raise_for_status()
        return r.json()
    raise RuntimeError("GET failed after retries (429/503).")


def _graph_delete(session: requests.Session, access_token: str, url: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    for _ in range(5):
        r = session.delete(url, headers=headers)
        if r.status_code in (429, 503):
            wait = int(r.headers.get("Retry-After", "2"))
            time.sleep(wait)
            continue
        if r.status_code == 401:
            raise RuntimeError("401 Unauthorized. Access token expired/invalid.")
        if r.status_code in (200, 202, 204):
            return
        r.raise_for_status()
    raise RuntimeError("DELETE failed after retries (429/503).")


def delete_all_pages_in_section(
    session: requests.Session,
    access_token: str,
    section_id: str,
    sleep_sec: float = 0.2,
) -> int:
    url = f"https://graph.microsoft.com/v1.0/me/onenote/sections/{quote(section_id)}/pages?$select=id,title&$top=100"

    deleted = 0
    while url:
        data = _graph_get(session, access_token, url)
        pages = data.get("value", [])

        for p in pages:
            page_id = p.get("id")
            title = p.get("title", "")
            if not page_id:
                continue

            del_url = f"https://graph.microsoft.com/v1.0/me/onenote/pages/{quote(page_id)}"
            _graph_delete(session, access_token, del_url)

            deleted += 1
            print(f"[DEL] {deleted}: {title} ({page_id})")

            if sleep_sec:
                time.sleep(sleep_sec)

        url = data.get("@odata.nextLink")

    return deleted


# ========= main =========

def main() -> None:
    if not ACCESS_TOKEN or not ACCESS_TOKEN.strip():
        raise RuntimeError("ACCESS_TOKEN is empty. Set it in config.py")

    dxl_dir = Path(DXL_DIR)
    if not dxl_dir.exists():
        raise RuntimeError(f"DXL_DIR not found: {dxl_dir}")

    dxl_files = sorted(dxl_dir.glob("*.dxl"))
    if not dxl_files:
        raise RuntimeError(f"No DXL files found in: {dxl_dir}")

    notebook_id = find_notebook_id(ACCESS_TOKEN, NOTEBOOK_NAME)
    section_id = find_section_id(ACCESS_TOKEN, notebook_id, SECTION_NAME)

    created = 0
    session = requests.Session()

    # ★ スクショが入り得るRichTextフィールド名（必要に応じて増やす）
    rich_fields = ["Detail", "Reason", "Temporary", "Parmanent"]

    try:
        for i, dxl_path in enumerate(dxl_files, start=1):
            base = os.path.basename(str(dxl_path))

            # ★ DXL -> (OneNoteRow, BinaryParts)
            note, parts = dxl_to_onenote_payload(str(dxl_path), rich_fields=rich_fields)

            title = _make_title(note, base)

            body_html = render_incident_like_page(note, source_file=base, row_no=i)

            page = _post_onenote_page_multipart(
                session=session,
                access_token=ACCESS_TOKEN,
                section_id=section_id,
                page_title=title,
                body_html=body_html,
                parts=parts,
            )

            web_url = (page.get("links", {}).get("oneNoteWebUrl", {}) or {}).get("href")
            created += 1
            print(f"[OK] {created}: title='{title}' images={len(parts)} url={web_url}")

            if SLEEP_SEC:
                time.sleep(SLEEP_SEC)

        print(f"Done. Created pages: {created}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
