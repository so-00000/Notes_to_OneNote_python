# main.py
import csv
import glob
import html
import os
import time
from typing import Dict, Any, Iterator, Tuple
from urllib.parse import quote

import requests

from config import ACCESS_TOKEN, NOTEBOOK_NAME, SECTION_NAME, CSV_DIR, TITLE_COLUMN, SLEEP_SEC
from find_id import find_notebook_id, find_section_id

from models import NoteRow
from renderer_rich import render_incident_like_page


def _post_onenote_page(
    session: requests.Session,
    access_token: str,
    section_id: str,
    page_title: str,
    body_html: str,
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
        "Content-Type": "application/xhtml+xml",
    }

    for _ in range(5):
        r = session.post(url, headers=headers, data=xhtml.encode("utf-8"))

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


def _iter_csv_rows(path: str) -> Iterator[Tuple[int, Dict[str, Any]]]:
    last_err: Exception | None = None

    for enc in ("utf-8-sig", "cp932"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise RuntimeError("CSV has no header row.")

                for i, row in enumerate(reader, start=1):
                    yield i, row
            return
        except UnicodeDecodeError as e:
            last_err = e
            continue

    raise RuntimeError(f"Cannot decode CSV: {path} (tried utf-8-sig, cp932). last_err={last_err}")


def _make_title(row: Dict[str, Any], base: str, row_no: int) -> str:
    candidates = []
    if TITLE_COLUMN:
        candidates.append(TITLE_COLUMN)
    candidates.append("DocumentNo")

    for key in candidates:
        v = (row.get(key) or "")
        v = str(v).strip()
        if v:
            return v

    return f"{base} row{row_no}"


def main() -> None:
    notebook_id = find_notebook_id(ACCESS_TOKEN, NOTEBOOK_NAME)
    section_id = find_section_id(ACCESS_TOKEN, notebook_id, SECTION_NAME)

    csv_files = sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
    if not csv_files:
        raise RuntimeError(f"No CSV files found in: {CSV_DIR}")

    created = 0
    session = requests.Session()

    try:
        for csv_path in csv_files:
            base = os.path.basename(csv_path)

            for row_no, row_dict in _iter_csv_rows(csv_path):
                title = _make_title(row_dict, base, row_no)

                # ✅ ここがレイアウトの本体：CSV1行→NoteRow→PDF風HTML
                note = NoteRow.from_csv_row(row_dict)
                body_html = render_incident_like_page(note, source_file=base, row_no=row_no)

                page = _post_onenote_page(
                    session=session,
                    access_token=ACCESS_TOKEN,
                    section_id=section_id,
                    page_title=title,
                    body_html=body_html,
                )

                web_url = (page.get("links", {}).get("oneNoteWebUrl", {}) or {}).get("href")
                created += 1
                print(f"[OK] {created}: title='{title}' url={web_url}")

                if SLEEP_SEC:
                    time.sleep(SLEEP_SEC)

        print(f"Done. Created pages: {created}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
