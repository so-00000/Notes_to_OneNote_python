from __future__ import annotations

import argparse
import csv
import html
import json
import locale
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
try:
    import msvcrt  # Windows console key polling
except ImportError:  # pragma: no cover
    msvcrt = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.data_type_config import get_data_type_settings
from main.services.graph_auth import build_access_token_provider
from main.services.graph_client import GraphClient, RateLimitExceededError

NO_LINK = "NO_LINK"
HAS_LINK_UNRESOLVED = "HAS_LINK_UNRESOLVED"
HAS_LINK_UNRESOLVED_CHECKED = "HAS_LINK_UNRESOLVED_CHECKED"
HAS_LINK_RESOLVED = "HAS_LINK_RESOLVED"


class UserCancelledError(Exception):
    """Raised when user requests cancellation via Esc key."""


@dataclass
class LinkRef:
    placeholder_id: str
    replicaid: str
    unid: str
    href: str
    label: str
    target_generated_id: str
    target_tag: str
    target_attrs: dict[str, str]


class _DocLinkHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[LinkRef] = []
        self._noteslink_stack: list[tuple[str, str]] = []
        self._element_stack: list[tuple[str, dict[str, str]]] = []
        self._current: Optional[dict[str, str]] = None
        self._current_target_tag = ""
        self._current_target_id = ""
        self._current_target_attrs: dict[str, str] = {}

    @staticmethod
    def _is_replaceable_tag(tag: str) -> bool:
        t = tag.lower()
        return t in {"div", "ol", "ul", "table", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def _find_replace_target(self) -> tuple[str, str, dict[str, str]]:
        div_fallback: tuple[str, str, dict[str, str]] | None = None
        for tag, attr in reversed(self._element_stack):
            generated_id = attr.get("id", "").strip()
            if not generated_id:
                continue
            if generated_id.startswith("noteslink-"):
                continue
            if not self._is_replaceable_tag(tag):
                continue
            if tag == "div":
                if div_fallback is None:
                    div_fallback = (tag, generated_id, dict(attr))
                continue
            return tag, generated_id, dict(attr)
        return div_fallback or ("", "", {})

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
        self._element_stack.append((t, attr))

        # OneNote page content may normalize our placeholder wrapper and keep
        # only data-id instead of id after the page is created.
        cid = attr.get("id", "") or attr.get("data-id", "")
        if cid.startswith("noteslink-"):
            self._noteslink_stack.append((t, cid))

        if t != "a":
            return
        pid = ""
        for _, item in reversed(self._noteslink_stack):
            if item:
                pid = item
                break
        target_tag, target_generated_id, target_attrs = self._find_replace_target()
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
        self._current_target_tag = target_tag
        self._current_target_id = target_generated_id
        self._current_target_attrs = target_attrs

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
                    target_generated_id=self._current_target_id,
                    target_tag=self._current_target_tag,
                    target_attrs=dict(self._current_target_attrs),
                )
            )
            self._current = None
            self._current_target_tag = ""
            self._current_target_id = ""
            self._current_target_attrs = {}
            return

        if self._noteslink_stack and self._noteslink_stack[-1][0] == t:
            self._noteslink_stack.pop()
        if self._element_stack and self._element_stack[-1][0] == t:
            self._element_stack.pop()


class EscCancellationMonitor:
    """
    Lightweight Esc-key monitor.
    Checks at a coarse interval to minimize impact on processing.
    """

    def __init__(self, check_interval_sec: float = 1.0) -> None:
        self._check_interval_sec = check_interval_sec
        self._next_check_at = time.monotonic()

    def check(self) -> None:
        if msvcrt is None:
            return

        now = time.monotonic()
        if now < self._next_check_at:
            return
        self._next_check_at = now + self._check_interval_sec

        while msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x1b":
                raise UserCancelledError("Esc key pressed.")
            if ch in ("\x00", "\xe0") and msvcrt.kbhit():
                _ = msvcrt.getwch()


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


def _safe_console_text(value: object) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or locale.getpreferredencoding(False) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _log_row_sample(rows: list[dict[str, str]], *, limit: int = 3) -> None:
    if not rows:
        print("[INFO] unresolved sample: []")
        return
    keys = ("source_id", "onenote_page_id", "link_resolution_status", "title")
    for row in rows[:limit]:
        sample = {k: _safe_console_text(row.get(k, "")) for k in keys}
        print(f"[INFO] unresolved sample: {sample}")


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


def _build_anchor_html(link: LinkRef, web_url: str) -> str:
    rep = html.escape(link.replicaid, quote=True)
    uid = html.escape(link.unid, quote=True)
    href = html.escape(web_url, quote=True)
    label = html.escape(link.label or f"{link.replicaid}_{link.unid}")
    return (
        f"<a class='notes-link' data-notes-replicaid='{rep}' "
        f"data-notes-unid='{uid}' href='{href}'>{label}</a>"
    )


def _build_replacement_content(link: LinkRef, web_url: str) -> str:
    anchor = _build_anchor_html(link, web_url)
    tag = (link.target_tag or "").strip().lower()
    if not tag:
        return anchor

    preserved_attrs: list[str] = []
    for key, value in (link.target_attrs or {}).items():
        k = (key or "").strip().lower()
        if not k or k == "id":
            continue
        if k == "data-id":
            continue
        if k.startswith("data-notes-"):
            continue
        preserved_attrs.append(f"{html.escape(k, quote=True)}='{html.escape(value, quote=True)}'")
    attrs_text = f" {' '.join(preserved_attrs)}" if preserved_attrs else ""
    return f"<{tag}{attrs_text}>{anchor}</{tag}>"


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


def _rate_limit_wait_seconds(exc: RateLimitExceededError, attempt: int) -> float:
    retry_after = (exc.retry_after or "").strip()
    if retry_after.isdigit():
        return float(retry_after)
    return min(12.0, 2.0 * (2 ** (attempt - 1)))


def _get_page_content_with_retry(
    client: GraphClient,
    page_id: str,
    *,
    max_not_ready_retries: int = 8,
    max_rate_limit_retries: int = 5,
) -> str:
    not_ready_attempt = 0
    rate_limit_attempt = 0
    while True:
        try:
            return client.get_onenote_page_content(page_id, include_ids=True)
        except RateLimitExceededError as exc:
            rate_limit_attempt += 1
            if rate_limit_attempt >= max_rate_limit_retries:
                raise
            wait_seconds = _rate_limit_wait_seconds(exc, rate_limit_attempt)
            print(
                f"[RETRY] page content rate-limited: page_id={page_id} "
                f"attempt={rate_limit_attempt}/{max_rate_limit_retries} wait={wait_seconds:.1f}s"
            )
            time.sleep(wait_seconds)
        except Exception as exc:
            not_ready_attempt += 1
            if (not _is_not_ready_20102(exc)) or not_ready_attempt >= max_not_ready_retries:
                raise
            wait_seconds = min(8.0, 1.0 * (2 ** (not_ready_attempt - 1)))
            print(
                f"[RETRY] page content not ready yet: page_id={page_id} "
                f"attempt={not_ready_attempt}/{max_not_ready_retries} wait={wait_seconds:.1f}s"
            )
            time.sleep(wait_seconds)


def _update_page_doclinks_with_retry(
    client: GraphClient,
    *,
    page_id: str,
    commands: list[dict[str, str]],
    max_rate_limit_retries: int = 5,
) -> None:
    for attempt in range(1, max_rate_limit_retries + 1):
        try:
            client.update_onenote_page_doclinks(page_id=page_id, commands=commands)
            return
        except RateLimitExceededError as exc:
            if attempt >= max_rate_limit_retries:
                raise
            wait_seconds = _rate_limit_wait_seconds(exc, attempt)
            print(
                f"[RETRY] doclink update rate-limited: page_id={page_id} "
                f"attempt={attempt}/{max_rate_limit_retries} wait={wait_seconds:.1f}s"
            )
            time.sleep(wait_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="OneNote や CSV の更新は行わず、解決可否の確認だけ行う。",
    )
    args = parser.parse_args()

    view_name = get_data_type_settings().view_name

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
    print(f"[INFO] source_to_web_url_count={len(source_to_web_url)}")

    unresolved_rows = [
        row
        for row in rows
        if (row.get("link_resolution_status") or "").strip() == HAS_LINK_UNRESOLVED
    ]
    print(f"[INFO] view={view_name} unresolved_pages={len(unresolved_rows)} total_rows={len(rows)}")
    _log_row_sample(unresolved_rows)

    patched_pages = 0
    patched_links = 0
    unresolved_links = 0
    no_placeholder_links = 0

    client = GraphClient(build_access_token_provider())
    cancel_monitor = EscCancellationMonitor(check_interval_sec=1.0)
    stop_requested = False
    try:
        print("[INFO] Press Esc to request cancellation (stops after the current page is finalized).")
        for row in unresolved_rows:
            cancel_monitor.check()
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
                    target_generated_id = (link.target_generated_id or "").strip()
                    if target_generated_id:
                        commands.append(
                            {
                                "target": target_generated_id,
                                "action": "replace",
                                "content": _build_replacement_content(link, web_url),
                            }
                        )
                        replaced_refs += 1
                        continue
                    no_placeholder += 1
                if commands and not args.dry_run:
                    _update_page_doclinks_with_retry(client, page_id=page_id, commands=commands)
                if commands:
                    patched_pages += 1
                    patched_links += replaced_refs

                unresolved_links += missing
                no_placeholder_links += no_placeholder
                row["link_resolution_status"] = (
                    HAS_LINK_RESOLVED
                    if (missing == 0 and no_placeholder == 0)
                    else HAS_LINK_UNRESOLVED_CHECKED
                )
                print(
                    f"[PAGE] source_id={source_id} commands={len(commands)} replaced={replaced_refs} "
                    f"missing={missing} no_placeholder={no_placeholder} "
                    f"state={row['link_resolution_status']}"
                )
            except Exception as exc:
                row["link_resolution_status"] = HAS_LINK_UNRESOLVED_CHECKED
                print(f"[WARN] source_id={source_id} page_id={page_id} error={exc}")

            if not args.dry_run:
                _write_csv_rows(csv_path, headers, rows)

            try:
                cancel_monitor.check()
            except UserCancelledError:
                stop_requested = True
                print(f"[CANCELLED] Stopped by Esc after finalizing source_id={source_id}")
                break
    except UserCancelledError:
        stop_requested = True
        print("[CANCELLED] Stopped by Esc before starting the next page.")
    finally:
        client.close()

    if not args.dry_run and not stop_requested:
        _write_csv_rows(csv_path, headers, rows)

    print(
        f"[DONE] patched_pages={patched_pages} patched_links={patched_links} "
        f"unresolved_links={unresolved_links} no_placeholder_links={no_placeholder_links} "
        f"dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
