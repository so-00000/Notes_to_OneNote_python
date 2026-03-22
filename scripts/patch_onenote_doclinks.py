from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.ignore_git import token
from main.models.models import DocLinkPlaceholder
from main.services.graph_client import GraphClient


def _load_log(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"log not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _build_doc_index(log: dict) -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in log.get("pages", []):
        doc_key = entry.get("doc_key")
        web_url = entry.get("web_url")
        if doc_key and web_url:
            index[doc_key] = web_url
    return index


def _load_placeholders(raw: list[dict]) -> list[DocLinkPlaceholder]:
    out: list[DocLinkPlaceholder] = []
    for item in raw:
        try:
            out.append(DocLinkPlaceholder(**item))
        except TypeError:
            continue
    return out


def main() -> int:
    log_path = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "logs" / "onenote_link_map.json"
    )

    log = _load_log(log_path)
    doc_index = _build_doc_index(log)

    access_token = token.ACCESS_TOKEN
    if not access_token or not access_token.strip():
        raise RuntimeError("ACCESS_TOKEN is empty.")

    client = GraphClient(access_token)
    patched = 0

    try:
        for entry in log.get("pages", []):
            page_id = entry.get("page_id")
            if not page_id:
                continue

            placeholders = _load_placeholders(entry.get("placeholders") or [])
            if not placeholders:
                continue

            updates = []
            for placeholder in placeholders:
                target_key = f"{placeholder.target_replicaid}:{placeholder.target_unid}"
                web_url = doc_index.get(target_key)
                if not web_url:
                    continue
                updates.append((placeholder, web_url))

            if updates:
                client.update_onenote_page_doclinks(page_id=page_id, updates=updates)
                patched += len(updates)
    finally:
        client.close()

    print(f"Done. Patched links: {patched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
