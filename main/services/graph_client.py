from __future__ import annotations

import html
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
from urllib.parse import quote

import requests
import logging

from ..models.models import PagePayload, Segment
from ..logging.graph_logging import mask_headers, summarize_request_kwargs, truncate_text
from .segments_body import _segment_to_html, _inject_segments_into_body, _inject_first_segments
import json
from typing import List



from pprint import pprint

MultipartPart = Tuple[str, bytes, str]  # (filename, content, content_type)

@dataclass(frozen=True)
class GraphRetryPolicy:
    """Graph APIリクエストのリトライ設定"""

    max_retries: int = 5
    retry_statuses: tuple[int, ...] = (429, 503)
    default_retry_after: int = 2


class GraphClient:
    """
    Microsoft Graph APIの呼び出しをシンプルに扱うためのクライアント

    - 401は即座に例外
    - 429/503はRetry-Afterで待って再試行
    - 成功時はResponseを返す
    """

    def __init__(
        self,
        access_token: str,
        *,
        session: Optional[requests.Session] = None,
        retry_policy: Optional[GraphRetryPolicy] = None,
    ) -> None:
        self._access_token = access_token
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._retry = retry_policy or GraphRetryPolicy()
        self._logger = logging.getLogger(__name__)


    def close(self) -> None:
        """必要に応じて内部Sessionを閉じる。"""
        if self._owns_session:
            self._session.close()
    
    def _merged_headers(self, headers: Optional[dict]) -> dict:
        # 呼び出し側が Authorization を渡しても上書きされるように固定
        merged = dict(headers or {})
        merged["Authorization"] = f"Bearer {self._access_token}"
        return merged


    # ==============================
    # リクエスト送信・リトライ制御（共通）
    # ==============================
    #
    # ■ 役割
    # - Graph API への実送信と、429/503 リトライ制御を集約。
    # - multipart / JSON など「送信形式の違い」は呼び出し側で request_kwargs を作る。
    #
    #
    # ■ エラーハンドリング
    # - 429/503: Retry-After を見て待機→再試行する。
    # - 401: アクセストークン失効/不正として例外にする。
    # - その他: raise_for_status() に委ねる（4xx/5xx は例外）。
    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict] = None,
        **request_kwargs: Any,
    ) -> requests.Response:

        # ヘッダー構築（アクセストークンなど）
        merged_headers = self._merged_headers(headers)

        # 送信前ログ（DEBUG推奨）
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

        for attempt in range(1, self._retry.max_retries + 1):
            start = time.perf_counter()

            resp = self._session.request(
                method,
                url,
                headers=merged_headers,
                **request_kwargs,
            )

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # リトライ対象（429/503）
            if resp.status_code in self._retry.retry_statuses:
                wait = int(resp.headers.get("Retry-After", self._retry.default_retry_after))
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

            # 401 は即例外
            if resp.status_code == 401:
                self._logger.error(
                    "Graph unauthorized: %s %s status=401 elapsed=%sms body=%s",
                    method,
                    url,
                    elapsed_ms,
                    truncate_text(resp.text, limit=500),
                )
                raise RuntimeError("401 Unauthorized. Access token expired/invalid.")

            # その他のエラー（raise_for_status）
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

            # 成功ログ（INFO）
            self._logger.info(
                "Graph request success: %s %s status=%s elapsed=%sms",
                method,
                url,
                resp.status_code,
                elapsed_ms,
            )
            return resp

        self._logger.error(
            "%s failed after retries (%s). last_exc=%s",
            method,
            self._retry.retry_statuses,
            last_exc,
        )
        raise RuntimeError(f"{method} failed after retries (429/503).")


    # ==============================
    # Graph API リクエスト（multipart/form-data）
    # ==============================
    #
    # ■ 用途
    # - HTML(Presentation) と画像/添付(バイナリ)を同じPOSTで送る必要があるケースに使用する。
    #
    # ■ data_parts（= multipart の各パート）
    # - dict のキーが “パート名” になる（例: "Presentation", "image1", "file1"）。
    # - "Presentation" は必須で、ページ本文の XHTML/HTML を入れる。
    # - 画像/添付は本文HTML内で `name:パート名` を参照して貼り付ける。
    #
    # ■ 実装メモ
    # - requests の `files=` に data_parts を渡すと multipart/form-data になる。
    # - 送信とリトライは共通関数 `_request_with_retry()` に委譲する。
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


    # ==============================
    # Graph API リクエスト（JSON / 通常通信）
    # ==============================
    #
    # ■ 用途
    # - Graph API の大半は JSON（またはボディ無し）で通信するため、この入口を使う。
    # - GET/DELETE のようにボディが不要なリクエストもここに寄せると迷いにくい。
    #
    # ■ 引数の使い分け
    # - json_body: POST/PATCH などで送る JSON ボディ。
    # - params: URLクエリ（`?$select=...&$top=...` のような OData パラメータ）。
    #
    # ■ 実装メモ
    # - requests の `json=` を使うと Content-Type: application/json が自動設定される。
    # - 送信とリトライは共通関数 `_request_with_retry()` に委譲する。
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
        """GETしてJSONを返す。"""
        return self._request_json("GET", url).json()

    def delete(self, url: str) -> None:
        """DELETEして結果を確認する。"""
        self._request_json("DELETE", url)




    def update_onenote_page_segments(
        self,
        *,
        page_id: str,
        segments: List[Segment],
        name_prefix: str = "p",
    ) -> None:
        """
        既存ページに対して、アンカー（data-id）をターゲットに
        画像/添付を append で差し込む。

        multipart:
        - Commands: patch commands (application/json)
        - p1..pN  : binary parts
        """

        url = f"https://graph.microsoft.com/v1.0/me/onenote/pages/{page_id}/content"

        commands = []
        data_parts = {}

        # Commands パートは必須（バイナリ参照するため） :contentReference[oaicite:5]{index=5}
        # → ただし data_parts に入れるのは最後にまとめてOK

        for i, seg in enumerate(segments, start=1):
            part_name = f"{name_prefix}{i}"
            bp = seg.binary_part

            # 1) HTML断片（この seg 用に name:part_name を参照するHTMLを作る）
            if bp.kind == "image":
                style = "max-width:100%;"
                if bp.width:
                    style += f" width:{bp.width}px;"
                if bp.height:
                    style += f" height:{bp.height}px;"
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

            # 2) patch command：アンカー（data-id）に append
            # data-id を付けた要素は #<data-id> で target 指定できる :contentReference[oaicite:6]{index=6}
            commands.append(
                {
                    "target": f"#{seg.segment_id}",
                    "action": "append",
                    "content": content_html,
                }
            )

            # 3) バイナリパート追加
            data_parts[part_name] = (bp.filename, bp.data, bp.content_type)

        # Commands パートを multipart に入れる
        commands_json = json.dumps(commands, ensure_ascii=False).encode("utf-8")
        data_parts["Commands"] = ("commands.json", commands_json, "application/json")

        # PATCH multipart
        res = self._request_multipart("PATCH", url, data_parts=data_parts)
        res.raise_for_status()




    def create_onenote_page(
        self,
        *,
        section_id: str,
        page_payload: PagePayload,
    ) -> dict:
        url = f"https://graph.microsoft.com/v1.0/me/onenote/sections/{section_id}/pages"

        # Graph制約: Presentation + バイナリ最大5
        MAX_BIN_PER_REQUEST = 3
        
        all_segments = list(page_payload.segment_list or [])
        firstSeg = all_segments[:MAX_BIN_PER_REQUEST]
        restSeg = all_segments[MAX_BIN_PER_REQUEST:]


        # 初回送信分の作成（上限件数までバイナリデータセグメント埋め込みを行ったHTML作成）
        body_html, parts = _inject_first_segments(page_payload.body_html, firstSeg, name_prefix="p")

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

        res = self._request_multipart("POST", url, data_parts=data_parts)
        res.raise_for_status()
        page = res.json()
        page_id = page["id"]

        # 残りがあれば PATCH で 5個ずつ埋めていく
        for off in range(0, len(restSeg), MAX_BIN_PER_REQUEST):
            chunk = restSeg[off : off + MAX_BIN_PER_REQUEST]
            self.update_onenote_page_segments(page_id=page_id, segments=chunk)

        return page