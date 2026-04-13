from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
import time
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main.ignore_git.connection import GRAPH_ONENOTE_BASE_URL
from main.services.app_context import build_graph_client, load_app_settings, resolve_target_notebook_id

PAGE_BATCH_SIZE = 100


@dataclass(frozen=True)
class SectionCount:
    section_id: str
    section_name: str
    path: str
    page_count: int


@dataclass(frozen=True)
class SectionCountError:
    section_id: str
    path: str
    error: str


def _paged_items(client, url: str) -> list[dict]:
    items: list[dict] = []
    next_url = url
    while next_url:
        payload = client.get_json(next_url)
        items.extend(payload.get("value", []))
        next_url = payload.get("@odata.nextLink")
    return items


def _list_notebook_sections(client, notebook_id: str) -> list[dict]:
    url = (
        f"{GRAPH_ONENOTE_BASE_URL}/notebooks/{quote(notebook_id)}/sections"
        "?$select=id,displayName"
    )
    return _paged_items(client, url)


def _list_notebook_section_groups(client, notebook_id: str) -> list[dict]:
    url = (
        f"{GRAPH_ONENOTE_BASE_URL}/notebooks/{quote(notebook_id)}/sectionGroups"
        "?$select=id,displayName"
    )
    return _paged_items(client, url)


def _list_child_section_groups(client, section_group_id: str) -> list[dict]:
    url = (
        f"{GRAPH_ONENOTE_BASE_URL}/sectionGroups/{quote(section_group_id)}/sectionGroups"
        "?$select=id,displayName"
    )
    return _paged_items(client, url)


def _list_section_group_sections(client, section_group_id: str) -> list[dict]:
    url = (
        f"{GRAPH_ONENOTE_BASE_URL}/sectionGroups/{quote(section_group_id)}/sections"
        "?$select=id,displayName"
    )
    return _paged_items(client, url)


def _count_pages_in_section(client, section_id: str) -> int:
    count_url = (
        f"{GRAPH_ONENOTE_BASE_URL}/sections/{quote(section_id)}/pages"
        "?$count=true&$top=1&$select=id"
    )
    payload = client.get_json(count_url)
    odata_count = payload.get("@odata.count")
    if isinstance(odata_count, int):
        return odata_count

    count = 0
    url = (
        f"{GRAPH_ONENOTE_BASE_URL}/sections/{quote(section_id)}/pages"
        f"?$select=id&$top={PAGE_BATCH_SIZE}"
    )
    while url:
        payload = client.get_json(url)
        count += len(payload.get("value", []))
        url = payload.get("@odata.nextLink")
    return count


def _count_pages_in_section_with_retry(
    client,
    section_id: str,
    *,
    retries: int = 3,
    sleep_seconds: float = 2.0,
) -> int:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _count_pages_in_section(client, section_id)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            print(
                f"[WARN] count retry {attempt}/{retries} "
                f"section_id={section_id} error={exc}"
            )
            time.sleep(sleep_seconds)

    assert last_error is not None
    raise last_error


def _collect_from_section_group(
    client,
    section_group_id: str,
    parent_path: str,
) -> tuple[list[SectionCount], list[SectionCountError]]:
    results: list[SectionCount] = []
    errors: list[SectionCountError] = []

    for section in _list_section_group_sections(client, section_group_id):
        section_id = str(section.get("id") or "").strip()
        section_name = str(section.get("displayName") or "").strip()
        if not section_id:
            continue
        path = f"{parent_path}/{section_name}" if parent_path else section_name
        try:
            results.append(
                SectionCount(
                    section_id=section_id,
                    section_name=section_name,
                    path=path,
                    page_count=_count_pages_in_section_with_retry(client, section_id),
                )
            )
        except Exception as exc:
            errors.append(
                SectionCountError(
                    section_id=section_id,
                    path=path,
                    error=str(exc),
                )
            )
            print(f"[WARN] skip section path={path} section_id={section_id} error={exc}")

    for child_group in _list_child_section_groups(client, section_group_id):
        child_group_id = str(child_group.get("id") or "").strip()
        child_group_name = str(child_group.get("displayName") or "").strip()
        if not child_group_id:
            continue
        child_path = f"{parent_path}/{child_group_name}" if parent_path else child_group_name
        child_results, child_errors = _collect_from_section_group(client, child_group_id, child_path)
        results.extend(child_results)
        errors.extend(child_errors)

    return results, errors


def count_pages_per_section() -> tuple[list[SectionCount], list[SectionCountError]]:
    settings = load_app_settings()
    client = build_graph_client(settings)

    try:
        notebook_id = resolve_target_notebook_id(client, settings)
        results: list[SectionCount] = []
        errors: list[SectionCountError] = []

        for section in _list_notebook_sections(client, notebook_id):
            section_id = str(section.get("id") or "").strip()
            section_name = str(section.get("displayName") or "").strip()
            if not section_id:
                continue
            try:
                results.append(
                    SectionCount(
                        section_id=section_id,
                        section_name=section_name,
                        path=section_name,
                        page_count=_count_pages_in_section_with_retry(client, section_id),
                    )
                )
            except Exception as exc:
                errors.append(
                    SectionCountError(
                        section_id=section_id,
                        path=section_name,
                        error=str(exc),
                    )
                )
                print(
                    f"[WARN] skip section path={section_name} "
                    f"section_id={section_id} error={exc}"
                )

        for group in _list_notebook_section_groups(client, notebook_id):
            group_id = str(group.get("id") or "").strip()
            group_name = str(group.get("displayName") or "").strip()
            if not group_id:
                continue
            child_results, child_errors = _collect_from_section_group(client, group_id, group_name)
            results.extend(child_results)
            errors.extend(child_errors)

        return (
            sorted(results, key=lambda item: item.path.casefold()),
            sorted(errors, key=lambda item: item.path.casefold()),
        )
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count OneNote pages per section in the configured notebook."
    )
    parser.add_argument(
        "--include-id",
        action="store_true",
        help="Include section IDs in the output.",
    )
    args = parser.parse_args()

    results, errors = count_pages_per_section()
    total_pages = sum(item.page_count for item in results)
    print(
        f"[INFO] sections={len(results)} total_pages={total_pages} "
        f"failed_sections={len(errors)}"
    )
    for item in results:
        if args.include_id:
            print(f"{item.page_count:>6}  {item.path}  ({item.section_id})")
        else:
            print(f"{item.page_count:>6}  {item.path}")
    if errors:
        print("[WARN] failed sections:")
        for item in errors:
            if args.include_id:
                print(f"[WARN] {item.path}  ({item.section_id})  error={item.error}")
            else:
                print(f"[WARN] {item.path}  error={item.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
