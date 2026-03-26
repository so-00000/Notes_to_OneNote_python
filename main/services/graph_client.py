from __future__ import annotations

import csv
import html
import re
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import quote, urlsplit

import requests
import logging

from main.ignore_git.connection import GRAPH_ONENOTE_BASE_URL
from main.models.models import PagePayload, Segment
from main.logging.graph_logging import mask_headers, summarize_request_kwargs, truncate_text
from main.services.segments_body import _inject_first_segments
from main.services.layout_constants import (
    LEGACY_CONTENT_WIDTH,
    LEGACY_CONTENT_WIDTH_PX,
    MAX_CONTENT_WIDTH,
    MAX_CONTENT_WIDTH_PX,
)
import json
from typing import List

MultipartPart = Tuple[str, bytes, str]  # (filename, content, content_type)
MAX_MULTIPART_BINARY_PARTS = 5
MAX_GRAPH_MULTIPART_REQUEST_BYTES = 3_500_000
MAX_GRAPH_MULTIPART_PART_BYTES = 25 * 1024 * 1024


class RateLimitExceededError(RuntimeError):
    """Raised when Graph returns 429 and processing should stop."""

    def __init__(
        self,
        *,
        method: str,
        url: str,
        status: int,
        retry_after: str,
        request_id: str,
        client_request_id: str,
        body: str,
    ) -> None:
        super().__init__(f"{method} rate-limited after retries (status={status}).")
        self.method = method
        self.url = url
        self.status = status
        self.retry_after = retry_after
        self.request_id = request_id
        self.client_request_id = client_request_id
        self.body = body


class RequestBudgetExceededError(RuntimeError):
    """Raised before sending a request that would exceed the per-run budget."""

    def __init__(self, *, request_count: int, max_requests_per_run: int) -> None:
        super().__init__(
            f"request budget exceeded ({request_count}/{max_requests_per_run})."
        )
        self.request_count = request_count
        self.max_requests_per_run = max_requests_per_run


@dataclass(frozen=True)
class GraphRetryPolicy:
    """Graph API リトライ設定。"""

    max_retries: int = 2
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    default_retry_after: int = 2
    max_backoff_seconds: int = 12


class GraphClient:
    """OneNote 操作向けの Graph API クライアント。"""

    def __init__(
        self,
        access_token: str,
        *,
        session: Optional[requests.Session] = None,
        retry_policy: Optional[GraphRetryPolicy] = None,
        max_requests_per_run: Optional[int] = None,
    ) -> None:
        self._access_token = access_token
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._retry = retry_policy or GraphRetryPolicy()
        self._logger = logging.getLogger(__name__)
        self._request_count_log_path = (
            Path(__file__).resolve().parent.parent / "request_count_log.csv"
        )
        self._max_requests_per_run = max_requests_per_run
        self._request_count = 0

    def _segment_payload_size(self, seg: Segment) -> int:
        return len(seg.binary_part.data)

    def _chunk_segments_for_multipart(
        self,
        segments: List[Segment],
        *,
        max_bin_per_request: int = MAX_MULTIPART_BINARY_PARTS,
        max_request_bytes: int = MAX_GRAPH_MULTIPART_REQUEST_BYTES,
        request_overhead_bytes: int,
    ) -> list[List[Segment]]:
        chunks: list[list[Segment]] = []
        current: list[Segment] = []
        current_bytes = request_overhead_bytes

        for seg in segments:
            seg_bytes = self._segment_payload_size(seg)
            if seg_bytes > MAX_GRAPH_MULTIPART_PART_BYTES:
                raise ValueError(
                    "Binary part exceeds Microsoft Graph OneNote multipart part limit "
                    f"({seg.binary_part.filename}: {seg_bytes} bytes > {MAX_GRAPH_MULTIPART_PART_BYTES} bytes)."
                )

            if seg_bytes + request_overhead_bytes > max_request_bytes:
                raise ValueError(
                    "Binary part exceeds safe Microsoft Graph OneNote multipart request size "
                    f"({seg.binary_part.filename}: {seg_bytes} bytes)."
                )

            would_exceed_part_count = len(current) >= max_bin_per_request
            would_exceed_request_size = current_bytes + seg_bytes > max_request_bytes
            if current and (would_exceed_part_count or would_exceed_request_size):
                chunks.append(current)
                current = []
                current_bytes = request_overhead_bytes

            current.append(seg)
            current_bytes += seg_bytes

        if current:
            chunks.append(current)

        return chunks


    def _normalize_onenote_html(self, body_html: str) -> str:
        normalized = body_html
        # Normalize line endings first.
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        # Force shared max width for template/style fragments.
        legacy_width_escaped = re.escape(LEGACY_CONTENT_WIDTH)
        legacy_px_escaped = re.escape(str(LEGACY_CONTENT_WIDTH_PX))
        normalized = re.sub(
            rf"(?i)max-width\s*:\s*{legacy_width_escaped}",
            f"max-width:{MAX_CONTENT_WIDTH}",
            normalized,
        )
        normalized = re.sub(
            rf"(?i)width\s*:\s*{legacy_width_escaped}",
            f"width:{MAX_CONTENT_WIDTH}",
            normalized,
        )
        normalized = re.sub(
            rf"(?i)\bwidth\s*=\s*['\"]{legacy_px_escaped}['\"]",
            f"width='{MAX_CONTENT_WIDTH_PX}'",
            normalized,
        )
        # Collapse duplicated HTML line breaks into a single break.
        normalized = re.sub(r"(?is)(?:<br\s*/?>\s*){2,}", "<br/>", normalized)
        # Collapse duplicated blank lines in source HTML.
        normalized = re.sub(r"\n{2,}", "\n", normalized)
        return normalized

    def _append_request_count_log(
        self,
        *,
        method: str,
        url: str,
        status: int,
        elapsed_ms: int,
    ) -> None:
        try:
            path = self._request_count_log_path
            path.parent.mkdir(parents=True, exist_ok=True)
            needs_header = not path.exists()
            parts = urlsplit(url)
            url_path = parts.path
            if parts.query:
                url_path = f"{url_path}?{parts.query}"
            with path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if needs_header:
                    writer.writerow(
                        ["timestamp", "method", "status", "elapsed_ms", "url_path"]
                    )
                writer.writerow(
                    [
                        datetime.now().isoformat(timespec="seconds"),
                        method,
                        status,
                        elapsed_ms,
                        url_path,
                    ]
                )
        except Exception as e:
            self._logger.warning("request_count_log append failed: %s", e)

    @property
    def request_count(self) -> int:
        return self._request_count

    def _is_onenote_missing_resource_20102(
        self, response: Optional[requests.Response]
    ) -> bool:
        """
        OneNote API can briefly return 404/20102 right after page creation
        while the page ID has not propagated yet.
        """
        if response is None or response.status_code != 404:
            return False

        try:
            payload = response.json()
        except ValueError:
            return False

        if not isinstance(payload, dict):
            return False

        error = payload.get("error")
        if not isinstance(error, dict):
            return False

        return str(error.get("code")) == "20102"


    def close(self) -> None:
        """Close internal requests session if owned by this client."""
        if self._owns_session:
            self._session.close()
    
    def _merged_headers(self, headers: Optional[dict]) -> dict:
        # Authorization は常に現在のアクセストークンで上書きする。
        merged = dict(headers or {})
        merged["Authorization"] = f"Bearer {self._access_token}"
        return merged
    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict] = None,
        **request_kwargs: Any,
    ) -> requests.Response:

        merged_headers = self._merged_headers(headers)

        try:
            safe_headers = mask_headers(merged_headers)
            kw_summary = summarize_request_kwargs(dict(request_kwargs))
            self._logger.debug(
                "Graph request: %s %s headers=%s kwargs=%s",
                method,
                url,
                safe_headers,
                kw_summary,
            )
        except Exception as e:
            self._logger.debug("Graph request log failed: %s", e)

        last_exc: Optional[Exception] = None
        last_retryable_resp: Optional[requests.Response] = None

        for attempt in range(1, self._retry.max_retries + 1):
            if (
                method != "DELETE"
                and self._max_requests_per_run is not None
                and self._request_count >= self._max_requests_per_run
            ):
                raise RequestBudgetExceededError(
                    request_count=self._request_count,
                    max_requests_per_run=self._max_requests_per_run,
                )
            start = time.perf_counter()

            resp = self._session.request(
                method,
                url,
                headers=merged_headers,
                **request_kwargs,
            )
            self._request_count += 1

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._append_request_count_log(
                method=method,
                url=url,
                status=resp.status_code,
                elapsed_ms=elapsed_ms,
            )

            if resp.status_code == 429:
                last_retryable_resp = resp
                retry_debug = {
                    "status": resp.status_code,
                    "retry_after": resp.headers.get("Retry-After", ""),
                    "request_id": resp.headers.get("request-id", ""),
                    "client_request_id": resp.headers.get("client-request-id", ""),
                }
                body_preview = truncate_text(resp.text, limit=1000)
                self._logger.error(
                    "Graph rate-limited: %s %s status=%s elapsed=%sms response=%s body=%s",
                    method,
                    url,
                    resp.status_code,
                    elapsed_ms,
                    retry_debug,
                    body_preview,
                )
                print(
                    "[GRAPH FINAL ERROR] "
                    f"{method} {url} status={retry_debug['status']} "
                    f"retry_after={retry_debug['retry_after']} "
                    f"request_id={retry_debug['request_id']} "
                    f"client_request_id={retry_debug['client_request_id']} "
                    f"body={body_preview}"
                )
                raise RateLimitExceededError(
                    method=method,
                    url=url,
                    status=resp.status_code,
                    retry_after=retry_debug["retry_after"],
                    request_id=retry_debug["request_id"],
                    client_request_id=retry_debug["client_request_id"],
                    body=body_preview,
                )

            if resp.status_code in self._retry.retry_statuses:
                last_retryable_resp = resp
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None and str(retry_after).isdigit():
                    wait = int(retry_after)
                else:
                    wait = min(
                        self._retry.max_backoff_seconds,
                        self._retry.default_retry_after * (2 ** (attempt - 1)),
                    )
                self._logger.warning(
                    "Graph retryable response: %s %s status=%s attempt=%s/%s wait=%ss elapsed=%sms",
                    method,
                    url,
                    resp.status_code,
                    attempt,
                    self._retry.max_retries,
                    wait,
                    elapsed_ms,
                )
                time.sleep(wait)
                continue

            if resp.status_code == 401:
                self._logger.error(
                    "Graph unauthorized: %s %s status=401 elapsed=%sms body=%s",
                    method,
                    url,
                    elapsed_ms,
                    truncate_text(resp.text, limit=500),
                )
                raise RuntimeError("401 Unauthorized. Access token expired/invalid.")

            try:
                resp.raise_for_status()
            except Exception as e:
                last_exc = e
                self._logger.error(
                    "Graph request failed: %s %s status=%s elapsed=%sms body=%s",
                    method,
                    url,
                    resp.status_code,
                    elapsed_ms,
                    truncate_text(resp.text, limit=1000),
                )
                raise

            self._logger.info(
                "Graph request success: %s %s status=%s elapsed=%sms",
                method,
                url,
                resp.status_code,
                elapsed_ms,
            )
            return resp

        if last_retryable_resp is not None:
            retry_debug = {
                "status": last_retryable_resp.status_code,
                "retry_after": last_retryable_resp.headers.get("Retry-After", ""),
                "request_id": last_retryable_resp.headers.get("request-id", ""),
                "client_request_id": last_retryable_resp.headers.get("client-request-id", ""),
            }
            body_preview = truncate_text(last_retryable_resp.text, limit=1000)
            self._logger.error(
                "%s failed after retries (%s). last_exc=%s last_response=%s body=%s",
                method,
                self._retry.retry_statuses,
                last_exc,
                retry_debug,
                body_preview,
            )
            print(
                "[GRAPH FINAL ERROR] "
                f"{method} {url} status={retry_debug['status']} "
                f"retry_after={retry_debug['retry_after']} "
                f"request_id={retry_debug['request_id']} "
                f"client_request_id={retry_debug['client_request_id']} "
                f"body={body_preview}"
            )
        else:
            self._logger.error(
                "%s failed after retries (%s). last_exc=%s",
                method,
                self._retry.retry_statuses,
                last_exc,
            )
        raise RuntimeError(f"{method} failed after retries {self._retry.retry_statuses}.")

    def _request_multipart(
        self,
        method: str,
        url: str,
        *,
        data_parts: Dict[str, MultipartPart],
        headers: Optional[dict] = None,
    ) -> requests.Response:
        return self._request_with_retry(
            method,
            url,
            headers=headers,
            files=data_parts,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: Optional[Any] = None,
        headers: Optional[dict] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> requests.Response:
        return self._request_with_retry(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
        )






    def get_json(self, url: str) -> dict:
        """GETしてJSONレスポンスを返す。"""
        return self._request_json("GET", url).json()

    def get_onenote_page_content(self, page_id: str) -> str:
        """OneNoteページ本文をHTML文字列として取得する。"""
        url = f"{GRAPH_ONENOTE_BASE_URL}/pages/{quote(page_id)}/content"
        resp = self._request_json("GET", url, headers={"Accept": "text/html"})
        return resp.text

    def delete(self, url: str) -> None:
        """DELETEリクエストを送信する。"""
        self._request_json("DELETE", url)




    def update_onenote_page_segments(
        self,
        *,
        page_id: str,
        segments: List[Segment],
        name_prefix: str = "p",
        max_not_ready_retries: int = 14,
    ) -> None:
        """Append binary segments to an existing OneNote page."""

        # url = f"https://graph.microsoft.com/v1.0/me/onenote/pages/{page_id}/content"
        url = f"{GRAPH_ONENOTE_BASE_URL}/pages/{page_id}/content"


        commands = []
        data_parts = {}

        for i, seg in enumerate(segments, start=1):
            part_name = f"{name_prefix}{i}"
            bp = seg.binary_part

            # multipartのpart名(name:xxx)を参照するHTML断片を作る。
            if bp.kind == "image":
                style = f"max-width:{MAX_CONTENT_WIDTH}; width:100%; height:auto;"
                content_html = (
                    "<div style='margin:8px 0;'>"
                    f"<img src='name:{html.escape(part_name, quote=True)}' style='{style}'/>"
                    "</div>"
                )
            else:
                fn = html.escape(bp.filename, quote=True)
                mt = html.escape(bp.content_type or "application/octet-stream", quote=True)
                pn = html.escape(part_name, quote=True)
                content_html = (
                    "<div style='margin:8px 0; padding:10px; border:1px solid #e3e3e3; "
                    "border-radius:10px; background:#fff;'>"
                    f"<object data='name:{pn}' data-attachment='{fn}' type='{mt}'></object>"
                    "</div>"
                )

            sid = html.escape(seg.segment_id, quote=True)
            commands.append(
                {
                    "target": f"#{seg.segment_id}",
                    "action": "append",
                    "content": content_html,
                }
            )

            data_parts[part_name] = (bp.filename, bp.data, bp.content_type)

        commands_json = json.dumps(commands, ensure_ascii=False).encode("utf-8")
        data_parts["Commands"] = ("commands.json", commands_json, "application/json")

        # PATCH multipart
        for attempt in range(1, max_not_ready_retries + 1):
            try:
                self._request_multipart("PATCH", url, data_parts=data_parts)
                return
            except requests.exceptions.HTTPError as exc:
                response = exc.response
                is_not_ready = self._is_onenote_missing_resource_20102(response)
                if (not is_not_ready) or attempt >= max_not_ready_retries:
                    raise

                wait_seconds = min(8.0, 1.0 * (2 ** (attempt - 1)))
                self._logger.warning(
                    (
                        "OneNote page is not ready for PATCH yet; retrying "
                        "attempt=%s/%s wait=%.1fs page_id=%s"
                    ),
                    attempt,
                    max_not_ready_retries,
                    wait_seconds,
                    page_id,
                )
                time.sleep(wait_seconds)


    def update_onenote_page_doclinks(
        self,
        *,
        page_id: str,
        commands: List[dict[str, str]],
    ) -> None:
        """Apply doclink replacement commands to an existing OneNote page."""
        if not commands:
            return

        url = f"{GRAPH_ONENOTE_BASE_URL}/pages/{page_id}/content"
        commands_json = json.dumps(commands, ensure_ascii=False).encode("utf-8")
        data_parts = {
            "Commands": ("commands.json", commands_json, "application/json"),
        }
        self._request_multipart("PATCH", url, data_parts=data_parts)




    def create_onenote_page(
        self,
        *,
        section_id: str,
        page_payload: PagePayload,
    ) -> dict:
        page, rest_segments = self.create_onenote_page_base(
            section_id=section_id,
            page_payload=page_payload,
        )
        self.append_onenote_page_remaining_segments(
            page_id=page["id"],
            segments=rest_segments,
        )
        return page

    def create_onenote_page_base(
        self,
        *,
        section_id: str,
        page_payload: PagePayload,
        max_bin_per_request: int = MAX_MULTIPART_BINARY_PARTS,
    ) -> tuple[dict, List[Segment]]:
        url = f"{GRAPH_ONENOTE_BASE_URL}/sections/{section_id}/pages"

        all_segments = list(page_payload.segment_list or [])
        first_chunk = self._chunk_segments_for_multipart(
            all_segments,
            max_bin_per_request=max_bin_per_request,
            request_overhead_bytes=250_000,
        )
        firstSeg = first_chunk[0] if first_chunk else []
        restSeg = all_segments[len(firstSeg):]

        body_html, parts = _inject_first_segments(page_payload.body_html, firstSeg, name_prefix="p")
        body_html = self._normalize_onenote_html(body_html)

        xhtml = f"""<!DOCTYPE html>
        <html>
        <head>
        <title>{html.escape(page_payload.page_title)}</title>
        </head>
        <body>
        {body_html}
        </body>
        </html>"""

        data_parts = {
            "Presentation": ("presentation.html", xhtml.encode("utf-8"), "text/html"),
        }
        for part_name, bp in parts:
            data_parts[part_name] = (bp.filename, bp.data, bp.content_type)

        parts_summary = [
            {
                "part_name": part_name,
                "filename": bp.filename,
                "content_type": bp.content_type,
                "size": len(bp.data),
            }
            for part_name, bp in parts
        ]
        self._logger.info("Create OneNote page XHTML:\n%s", xhtml)
        self._logger.info(
            "Create OneNote page parts: count=%s parts=%s",
            len(parts_summary),
            parts_summary,
        )

        res = self._request_multipart("POST", url, data_parts=data_parts)
        res.raise_for_status()
        page = res.json()
        return page, restSeg

    def append_onenote_page_remaining_segments(
        self,
        *,
        page_id: str,
        segments: List[Segment],
        max_bin_per_request: int = MAX_MULTIPART_BINARY_PARTS,
    ) -> None:
        for chunk in self._chunk_segments_for_multipart(
            segments,
            max_bin_per_request=max_bin_per_request,
            request_overhead_bytes=32_000,
        ):
            self.update_onenote_page_segments(page_id=page_id, segments=chunk)

    def delete_onenote_page(
        self,
        *,
        page_id: str,
    ) -> None:
        url = f"{GRAPH_ONENOTE_BASE_URL}/pages/{quote(page_id)}"
        self.delete(url)
