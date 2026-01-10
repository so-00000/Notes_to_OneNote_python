from __future__ import annotations

import html
import time
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import quote

import requests

from .dxl_to_payload import BinaryPart


@dataclass(frozen=True)
class GraphRetryPolicy:
    """Graph APIのリトライ制御をまとめる小さな設定オブジェクト。"""

    max_retries: int = 5
    retry_statuses: tuple[int, ...] = (429, 503)
    default_retry_after: int = 2


class GraphClient:
    """
    Microsoft Graph APIの呼び出しをシンプルに扱うためのクライアント。

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

    def close(self) -> None:
        """必要に応じて内部Sessionを閉じる。"""
        if self._owns_session:
            self._session.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        files: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> requests.Response:
        """Graph APIの共通リクエスト処理（リトライ込み）。"""
        merged_headers = {"Authorization": f"Bearer {self._access_token}"}
        if headers:
            merged_headers.update(headers)

        for _ in range(self._retry.max_retries):
            response = self._session.request(method, url, headers=merged_headers, files=files)

            if response.status_code in self._retry.retry_statuses:
                wait = int(response.headers.get("Retry-After", self._retry.default_retry_after))
                time.sleep(wait)
                continue

            if response.status_code == 401:
                raise RuntimeError("401 Unauthorized. Access token expired/invalid.")

            response.raise_for_status()
            return response

        raise RuntimeError(f"{method} failed after retries (429/503).")

    def get_json(self, url: str) -> dict:
        """GETしてJSONを返す。"""
        return self._request("GET", url).json()

    def delete(self, url: str) -> None:
        """DELETEして結果を確認する。"""
        response = self._request("DELETE", url)
        if response.status_code not in (200, 202, 204):
            response.raise_for_status()

    def create_onenote_page(
        self,
        *,
        section_id: str,
        page_title: str,
        body_html: str,
        parts: Iterable[BinaryPart],
    ) -> dict:
        """
        OneNoteのページをmultipartで作成する。

        Graph制約によりPresentation含め最大6パートのため、画像は最大5件まで。
        """
        url = f"https://graph.microsoft.com/v1.0/me/onenote/sections/{quote(section_id)}/pages"

        # PresentationパートをXHTMLで作成
        xhtml = f"""<!DOCTYPE html>
<html>
  <head>
    <title>{html.escape(page_title)}</title>
  </head>
  <body>
{body_html}
  </body>
</html>"""

        files = {
            "Presentation": ("presentation.html", xhtml, "text/html"),
        }

        # Graph制約: Presentation + 画像(最大5)
        limited_parts = list(parts)[:5]
        for part in limited_parts:
            # <img src="name:{part.name}"> に対応するキーで送る
            files[part.name] = (part.filename, part.data, part.content_type)

        response = self._request("POST", url, files=files)
        return response.json()
