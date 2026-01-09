# find_id.py
import requests
from urllib.parse import quote


def _graph_get(access_token: str, url: str) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
    r.raise_for_status()
    return r.json()


def find_notebook_id(access_token: str, notebook_name: str) -> str:
    safe = notebook_name.replace("'", "''")
    url = (
        "https://graph.microsoft.com/v1.0/me/onenote/notebooks"
        f"?$filter=displayName eq '{safe}'&$select=id,displayName"
    )
    data = _graph_get(access_token, url)
    items = data.get("value", [])
    if not items:
        raise RuntimeError(f"Notebook not found: {notebook_name}")
    if len(items) > 1:
        raise RuntimeError(f"Notebook name is ambiguous (multiple found): {notebook_name}")
    return items[0]["id"]


def find_section_id(access_token: str, notebook_id: str, section_name: str) -> str:
    safe = section_name.replace("'", "''")
    url = (
        f"https://graph.microsoft.com/v1.0/me/onenote/notebooks/{quote(notebook_id)}/sections"
        f"?$filter=displayName eq '{safe}'&$select=id,displayName"
    )
    data = _graph_get(access_token, url)
    items = data.get("value", [])
    if not items:
        raise RuntimeError(f"Section not found in notebook: {section_name}")
    if len(items) > 1:
        raise RuntimeError(f"Section name is ambiguous (multiple found): {section_name}")
    return items[0]["id"]
