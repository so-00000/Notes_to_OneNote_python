from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from pprint import pprint
from typing import Optional
from urllib.parse import urlparse

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.data_type_config import get_data_type_settings
from main.services.graph_auth import build_access_token_provider
from main.services.graph_client import GraphClient

NO_LINK = "NO_LINK"
HAS_LINK_UNRESOLVED = "HAS_LINK_UNRESOLVED"
HAS_LINK_RESOLVED = "HAS_LINK_RESOLVED"


@dataclass
class LinkRef:
    placeholder_id: str
    replicaid: str
    unid: str
    href: str
    label: str


class _DocLinkHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[LinkRef] = []
        self._noteslink_stack: list[tuple[str, str]] = []
        self._current: Optional[dict[str, str]] = None

    @staticmethod
    def _parse_notes_href(href: str) -> tuple[str, str]:
        """Parse notes://server/replica/view/unid?OpenDocument"""
        try:
            parsed = urlparse(href)
            if parsed.scheme.lower() != "notes":
                return "", ""
            segs = [s for s in parsed.path.split("/") if s]
            if len(segs) < 3:
                return "", ""
            replicaid = segs[0].strip()
            unid = segs[2].strip()
            return replicaid, unid
        except Exception:
            return "", ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}

        cid = attr.get("id", "")
        if cid.startswith("noteslink-"):
            self._noteslink_stack.append((t, cid))

        if t != "a":
            return
        pid = ""
        for _, item in reversed(self._noteslink_stack):
            if item:
                pid = item
                break
        href = attr.get("href", "").strip()
        rep = attr.get("data-notes-replicaid", "").strip()
        uid = attr.get("data-notes-unid", "").strip()
        if (not rep or not uid) and href.lower().startswith("notes://"):
            rep2, uid2 = self._parse_notes_href(href)
            rep = rep or rep2
            uid = uid or uid2
        if not rep or not uid:
            return

        self._current = {
            "placeholder_id": pid,
            "replicaid": rep,
            "unid": uid,
            "href": href,
            "label": "",
        }

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["label"] += data

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "a" and self._current is not None:
            self.links.append(
                LinkRef(
                    placeholder_id=self._current["placeholder_id"],
                    replicaid=self._current["replicaid"],
                    unid=self._current["unid"],
                    href=self._current["href"],
                    label=self._current["label"].strip(),
                )
            )
            self._current = None
            return

        if self._noteslink_stack and self._noteslink_stack[-1][0] == t:
            self._noteslink_stack.pop()


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader.fieldnames or []), list(reader)
        except UnicodeDecodeError:
            continue
    return [], []


def _write_csv_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows([{h: r.get(h, "") for h in headers} for r in rows])


def _parse_doclinks(page_html: str) -> list[LinkRef]:
    parser = _DocLinkHtmlParser()
    parser.feed(page_html)
    return parser.links


def _load_mapping_headers(mapping_path: Path) -> list[str]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    common_path = mapping_path.parent.parent / "cmn_mapping.json"
    common_mapping = (
        json.loads(common_path.read_text(encoding="utf-8"))
        if common_path.exists()
        else {"common_columns": []}
    )
    common_keys = [c["key"] for c in common_mapping.get("common_columns", [])]
    headers = ["view_name", *common_keys]
    seen = set(headers)
    for view in mapping.get("views", {}).values():
        for col in view.get("view_columns", []):
            key = col.get("output_key")
            if key and key not in seen:
                headers.append(key)
                seen.add(key)
    return headers


def _build_source_to_web_url(doc_mapping_root: Path) -> dict[str, str]:
    source_to_web_url: dict[str, str] = {}
    for csv_path in sorted(doc_mapping_root.glob("*/migration_master.csv")):
        _, rows = _read_csv_rows(csv_path)
        for row in rows:
            source_id = (row.get("source_id") or "").strip()
            web_url = (row.get("onenote_web_url") or "").strip()
            if source_id and web_url and source_id not in source_to_web_url:
                source_to_web_url[source_id] = web_url
    return source_to_web_url


def _build_anchor_content(link: LinkRef, web_url: str) -> str:
    rep = html.escape(link.replicaid, quote=True)
    uid = html.escape(link.unid, quote=True)
    href = html.escape(web_url, quote=True)
    label = html.escape(link.label or f"{link.replicaid}_{link.unid}")
    anchor = (
        f"<a class='notes-link' data-notes-replicaid='{rep}' "
        f"data-notes-unid='{uid}' href='{href}'>{label}</a>"
    )
    pid = (link.placeholder_id or "").strip()
    if not pid:
        return anchor
    pid_safe = html.escape(pid, quote=True)
    return f"<span id='{pid_safe}' data-id='{pid_safe}'>{anchor}</span>"


def _is_not_ready_20102(exc: Exception) -> bool:
    if not isinstance(exc, requests.exceptions.HTTPError):
        return False
    response = exc.response
    if response is None or response.status_code != 404:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    return isinstance(error, dict) and str(error.get("code")) == "20102"


def _get_page_content_with_retry(
    client: GraphClient,
    page_id: str,
    *,
    max_not_ready_retries: int = 8,
) -> str:
    for attempt in range(1, max_not_ready_retries + 1):
        try:
            return client.get_onenote_page_content(page_id)
        except Exception as exc:
            if (not _is_not_ready_20102(exc)) or attempt >= max_not_ready_retries:
                raise
            wait_seconds = min(8.0, 1.0 * (2 ** (attempt - 1)))
            print(
                f"[RETRY] page content not ready yet: page_id={page_id} "
                f"attempt={attempt}/{max_not_ready_retries} wait={wait_seconds:.1f}s"
            )
            time.sleep(wait_seconds)
    raise RuntimeError(f"Failed to get page content after retries: {page_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--view-name",
        help="対象 View フォルダ名。未指定時は DATA_TYPE setting の view_name を使う。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="OneNote や CSV の更新は行わず、解決可否の確認だけ行う。",
    )
    args = parser.parse_args()

    view_name = args.view_name or get_data_type_settings().view_name

    mapping_path = REPO_ROOT / "main" / "resources" / "mapping" / view_name / "mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(f"mapping not found: {mapping_path}")

    csv_path = REPO_ROOT / "main" / "doc_mapping" / view_name / "migration_master.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"migration_master not found: {csv_path}")

    headers, rows = _read_csv_rows(csv_path)
    if not headers:
        raise RuntimeError(f"CSV is empty: {csv_path}")

    required_headers = _load_mapping_headers(mapping_path)
    for h in required_headers:
        if h not in headers:
            headers.append(h)
    if "link_resolution_status" not in headers:
        headers.append("link_resolution_status")

    # リンク先参照は main/doc_mapping 配下の migration_master.csv を横断して解決する
    doc_mapping_root = REPO_ROOT / "main" / "doc_mapping"
    source_to_web_url = _build_source_to_web_url(doc_mapping_root)
    pprint(source_to_web_url)

    unresolved_rows = [
        row
        for row in rows
        if (row.get("link_resolution_status") or "").strip() == HAS_LINK_UNRESOLVED
    ]
    print(f"[INFO] view={view_name} unresolved_pages={len(unresolved_rows)} total_rows={len(rows)}")
    pprint(unresolved_rows)

    patched_pages = 0
    patched_links = 0
    unresolved_links = 0
    no_placeholder_links = 0

    client = GraphClient(build_access_token_provider())
    try:
        for row in unresolved_rows:
            source_id = (row.get("source_id") or "").strip()
            page_id = (row.get("onenote_page_id") or "").strip()
            if not page_id:
                continue

            try:
                page_html = _get_page_content_with_retry(client, page_id)
                links = _parse_doclinks(page_html)
                if not links:
                    row["link_resolution_status"] = NO_LINK
                    print(f"[PAGE] source_id={source_id} links=0 state={NO_LINK}")
                    continue

                replaced_refs = 0
                missing = 0
                no_placeholder = 0
                commands: list[dict[str, str]] = []
                for link in links:
                    target_source_id = f"{link.replicaid}_{link.unid}"
                    web_url = source_to_web_url.get(target_source_id, "")
                    if not web_url:
                        missing += 1
                        continue
                    if link.href.strip() == web_url:
                        continue
                    pid = (link.placeholder_id or "").strip()
                    if pid:
                        commands.append(
                            {
                                "target": f"#{pid}",
                                "action": "replace",
                                "content": _build_anchor_content(link, web_url),
                            }
                        )
                        replaced_refs += 1
                        continue
                    no_placeholder += 1
                if commands and not args.dry_run:
                    client.update_onenote_page_doclinks(page_id=page_id, commands=commands)
                if commands:
                    patched_pages += 1
                    patched_links += replaced_refs

                unresolved_links += missing
                no_placeholder_links += no_placeholder
                row["link_resolution_status"] = (
                    HAS_LINK_RESOLVED if (missing == 0 and no_placeholder == 0) else HAS_LINK_UNRESOLVED
                )
                print(
                    f"[PAGE] source_id={source_id} commands={len(commands)} replaced={replaced_refs} "
                    f"missing={missing} no_placeholder={no_placeholder} "
                    f"state={row['link_resolution_status']}"
                )
            except Exception as exc:
                row["link_resolution_status"] = HAS_LINK_UNRESOLVED
                print(f"[WARN] source_id={source_id} page_id={page_id} error={exc}")
    finally:
        client.close()

    if not args.dry_run:
        _write_csv_rows(csv_path, headers, rows)

    print(
        f"[DONE] patched_pages={patched_pages} patched_links={patched_links} "
        f"unresolved_links={unresolved_links} no_placeholder_links={no_placeholder_links} "
        f"dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
