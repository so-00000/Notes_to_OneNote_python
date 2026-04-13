from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.ignore_git.connection import GRAPH_ONENOTE_BASE_URL
from main.services.app_context import (
    build_graph_client,
    load_app_settings,
    resolve_target_notebook_id,
    resolve_target_section_id,
)

COUNT_RETRIES = 3
COUNT_RETRY_SLEEP_SECONDS = 3.0
PAGE_BATCH_SIZE = 100
PAGE_PROGRESS_EVERY = 500


def _filtered_pages_url(section_id: str, *, top: int, count: bool) -> str:
    filter_expr = quote(f"parentSection/id eq '{section_id}'", safe="")
    count_part = "&$count=true" if count else ""
    return (
        f"{GRAPH_ONENOTE_BASE_URL}/pages"
        f"?$filter={filter_expr}&$select=id,title&$top={top}{count_part}"
    )


def _count_via_odata_count(client, section_id: str) -> int:
    payload = client.get_json(_filtered_pages_url(section_id, top=1, count=True))
    odata_count = payload.get("@odata.count")
    if isinstance(odata_count, int):
        return odata_count
    raise RuntimeError("@odata.count was not returned.")


def _count_via_paging(client, section_id: str) -> int:
    count = 0
    page_no = 0
    url = _filtered_pages_url(section_id, top=PAGE_BATCH_SIZE, count=False)

    while url:
        page_no += 1
        payload = client.get_json(url)
        batch = payload.get("value", [])
        count += len(batch)
        if count and count % PAGE_PROGRESS_EVERY == 0:
            print(f"[INFO] paged_count={count} fetched_pages={page_no}")
        url = payload.get("@odata.nextLink")

    return count


def count_pages_in_section_alt(*, section_name: str) -> int:
    settings = load_app_settings()
    client = build_graph_client(settings)

    try:
        notebook_id = resolve_target_notebook_id(client, settings)
        section_id = resolve_target_section_id(
            client,
            settings,
            notebook_id,
            section_name=section_name,
        )
        print(
            f"[INFO] notebook={settings.notebook_name} "
            f"section={section_name} section_id={section_id} mode=alt_pages_filter"
        )

        last_error: Exception | None = None
        for attempt in range(1, COUNT_RETRIES + 1):
            try:
                result = _count_via_odata_count(client, section_id)
                print(f"[INFO] strategy=alt_odata_count count={result}")
                return result
            except Exception as exc:
                last_error = exc
                if attempt < COUNT_RETRIES:
                    print(
                        f"[WARN] alt odata_count retry {attempt}/{COUNT_RETRIES} "
                        f"section={section_name} error={exc}"
                    )
                    time.sleep(COUNT_RETRY_SLEEP_SECONDS)

        print(
            f"[WARN] fallback=alt_paging section={section_name} "
            f"reason={last_error}"
        )
        result = _count_via_paging(client, section_id)
        print(f"[INFO] strategy=alt_paging count={result}")
        return result
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count pages in one target section via alternate /onenote/pages filter path."
    )
    parser.add_argument(
        "--section-name",
        default="",
        help="Target section name. If omitted, main/config.py SECTION_NAME is used.",
    )
    args = parser.parse_args()

    settings = load_app_settings()
    section_name = str(args.section_name or "").strip() or settings.section_name
    if not section_name:
        raise RuntimeError(
            "SECTION_NAME is empty. Pass --section-name or set SECTION_NAME in main/config.py"
        )

    count = count_pages_in_section_alt(section_name=section_name)
    print(f"[DONE] section={section_name} count={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
