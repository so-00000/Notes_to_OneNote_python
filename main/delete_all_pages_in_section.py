from __future__ import annotations

from main.services.graph_client import GraphClient


def delete_all_pages_in_section(client: GraphClient, section_id: str) -> int:
    """指定セクション内の全ページを削除する。"""
    url = f"https://graph.microsoft.com/v1.0/me/onenote/sections/{section_id}/pages"
    deleted = 0

    while url:
        payload = client.get_json(url)
        for page in payload.get("value", []):
            page_id = page.get("id")
            if not page_id:
                continue
            client.delete(f"https://graph.microsoft.com/v1.0/me/onenote/pages/{page_id}")
            deleted += 1

        url = payload.get("@odata.nextLink")

    return deleted
