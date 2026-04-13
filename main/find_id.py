# find_id.py
from urllib.parse import quote

from main.ignore_git.connection import GRAPH_SITE_RESOURCE
from main.services.graph_client import GraphClient

# ノートブック名から、NotebookIdを取得する
def find_notebook_id(client: GraphClient, notebook_name: str) -> str:
    safe = notebook_name.replace("'", "''")
    url = (
        f"https://graph.microsoft.com/{GRAPH_SITE_RESOURCE}/onenote/notebooks"
        f"?$filter=displayName eq '{safe}'&$select=id,displayName"
    )
    data = client.get_json(url)
    items = data.get("value", [])
    if not items:
        raise RuntimeError(f"Notebook not found: {notebook_name}")
    if len(items) > 1:
        raise RuntimeError(f"Notebook name is ambiguous (multiple found): {notebook_name}")
    return items[0]["id"]

# notebookId・セクション名から、SectionIdを取得する
def find_section_id(client: GraphClient, notebook_id: str, section_name: str) -> str:
    safe = section_name.replace("'", "''")
    url = (
        f"https://graph.microsoft.com/{GRAPH_SITE_RESOURCE}/onenote/notebooks/{quote(notebook_id)}/sections"
        f"?$filter=displayName eq '{safe}'&$select=id,displayName"
    )
    data = client.get_json(url)
    items = data.get("value", [])
    if not items:
        created = client.create_onenote_section(
            notebook_id=notebook_id,
            section_name=section_name,
        )
        section_id = str(created.get("id") or "").strip()
        if not section_id:
            raise RuntimeError(f"Section created but id missing: {section_name}")
        return section_id
    if len(items) > 1:
        raise RuntimeError(f"Section name is ambiguous (multiple found): {section_name}")
    return items[0]["id"]
