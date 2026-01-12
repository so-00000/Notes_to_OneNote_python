import time
from urllib.parse import quote

from main.services.graph_client import GraphClient

def delete_all_pages_in_section(
    client: GraphClient,
    section_id: str,
    sleep_sec: float = 0.2,
) -> int:
    url = (
        f"https://graph.microsoft.com/v1.0/me/onenote/sections/{quote(section_id)}/pages"
        f"?$select=id,title&$top=100"
    )

    deleted = 0
    while url:
        data = client.get_json(url)
        pages = data.get("value", [])

        for p in pages:
            page_id = p.get("id")
            title = p.get("title", "")
            if not page_id:
                continue

            del_url = f"https://graph.microsoft.com/v1.0/me/onenote/pages/{quote(page_id)}"
            client.delete(del_url)

            deleted += 1
            print(f"[DEL] {deleted}: {title} ({page_id})")

            if sleep_sec:
                time.sleep(sleep_sec)

        url = data.get("@odata.nextLink")

    return deleted
