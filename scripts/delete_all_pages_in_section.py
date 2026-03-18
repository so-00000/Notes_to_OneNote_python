from __future__ import annotations

from urllib.parse import quote

from main.ignore_git.connection import GRAPH_ONENOTE_BASE_URL


def delete_all_pages_in_section(client, section_id: str) -> int:
    """
    Delete all pages in the target section.
    Returns number of deleted pages.
    """
    deleted = 0
    url = f"{GRAPH_ONENOTE_BASE_URL}/sections/{quote(section_id)}/pages"

    while url:
        payload = client.get_json(url)
        for page in payload.get("value", []):
            page_id = (page.get("id") or "").strip()
            if not page_id:
                continue
            client.delete(f"{GRAPH_ONENOTE_BASE_URL}/pages/{quote(page_id)}")
            deleted += 1
        url = payload.get("@odata.nextLink")

    return deleted
