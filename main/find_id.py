# find_id.py
from urllib.parse import quote

from main.services.graph_client import GraphClient


def find_notebook_id(client: GraphClient, notebook_name: str) -> str:

    # site_id = "v1.0/me"
    site_id = "v1.0/sites/nipponham86.sharepoint.com,c366644f-cbe3-4821-8d09-6eed7fb27f7b,743a28d6-6865-40fc-bc93-9e8c825be55a"


    """表示名からノートブックIDを取得する。"""
    safe = notebook_name.replace("'", "''")
    url = (
        f"https://graph.microsoft.com/{site_id}/onenote/notebooks"
        f"?$filter=displayName eq '{safe}'&$select=id,displayName"
    )
    data = client.get_json(url)
    items = data.get("value", [])
    if not items:
        raise RuntimeError(f"Notebook not found: {notebook_name}")
    if len(items) > 1:
        raise RuntimeError(f"Notebook name is ambiguous (multiple found): {notebook_name}")
    return items[0]["id"]


def find_section_id(client: GraphClient, notebook_id: str, section_name: str) -> str:

    # site_id = "v1.0/me"
    site_id = "v1.0/sites/nipponham86.sharepoint.com,c366644f-cbe3-4821-8d09-6eed7fb27f7b,743a28d6-6865-40fc-bc93-9e8c825be55a"


    """表示名からセクションIDを取得する。"""
    safe = section_name.replace("'", "''")
    url = (
        f"https://graph.microsoft.com/{site_id}/onenote/notebooks/{quote(notebook_id)}/sections"
        f"?$filter=displayName eq '{safe}'&$select=id,displayName"
    )
    data = client.get_json(url)
    items = data.get("value", [])
    if not items:
        raise RuntimeError(f"Section not found in notebook: {section_name}")
    if len(items) > 1:
        raise RuntimeError(f"Section name is ambiguous (multiple found): {section_name}")
    return items[0]["id"]
