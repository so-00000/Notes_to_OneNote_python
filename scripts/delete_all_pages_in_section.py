from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote
from main.ignore_git.connection import GRAPH_ONENOTE_BASE_URL
from main.services.app_context import (
    build_graph_client,
    load_app_settings,
    resolve_target_notebook_id,
    resolve_target_section_id,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))



def _list_pages_in_section(client, section_id: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    url = f"{GRAPH_ONENOTE_BASE_URL}/sections/{quote(section_id)}/pages"

    while url:
        payload = client.get_json(url)
        for page in payload.get("value", []):
            page_id = str(page.get("id") or "").strip()
            title = str(page.get("title") or "").strip()
            if not page_id:
                continue
            pages.append({"id": page_id, "title": title})
        url = payload.get("@odata.nextLink")

    return pages


def delete_all_pages_in_section(*, dry_run: bool = False) -> int:
    """
    Delete all pages in the configured target section.
    Returns number of deleted pages.
    """
    settings = load_app_settings()
    client = build_graph_client(settings)

    try:
        notebook_id = resolve_target_notebook_id(client, settings)
        section_id = resolve_target_section_id(client, settings, notebook_id)
        print(
            f"[INFO] notebook={settings.notebook_name} "
            f"section={settings.section_name} section_id={section_id}"
        )

        pages = _list_pages_in_section(client, section_id)
        if dry_run:
            print(f"[DRY-RUN] pages={len(pages)}")
            for page in pages:
                print(f"- page_id={page['id']} title={page['title']}")
            return 0

        deleted = 0
        for page in pages:
            page_id = page["id"]
            if not page_id:
                continue
            client.delete(f"{GRAPH_ONENOTE_BASE_URL}/pages/{quote(page_id)}")
            deleted += 1
    finally:
        client.close()

    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show target section and page list without deleting pages.",
    )
    args = parser.parse_args()

    deleted = delete_all_pages_in_section(dry_run=args.dry_run)
    print(f"[DONE] dry_run={args.dry_run} deleted_pages={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
