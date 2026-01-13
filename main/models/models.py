from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal


# =========================
#  ページ作成用のコンテンツ一式
# =========================
@dataclass(slots=True)
class PagePayload:
    """
    Uploader（Graph送信）はこれを受け取り、制約（最大5バイナリ/回）に合わせて分割送信する。

    - page_title        ページタイトル
    - body_html         ページ本文（プレースホルダ込み）
    - segment_list      セグメントデータ全件（バイナリデータを内包）
    """
    page_title: str
    body_html: str
    segment_list: List[Segment] = field(default_factory=list)


# =========================
#  ページ作成（multipart）用のリクエストパラメータ
# =========================
@dataclass(slots=True)
class MultipartPageRequest:
    """
    Graph送信用の“ページ作成リクエスト（素材）”。

    Uploader/Client はこれを受け取り、
    Graph制約（最大5バイナリ/回）に合わせて分割しつつ送信する。

    - section_id: 送信先セクションID
    - page_title: ページタイトル
    - body_html:  本文HTML（プレースホルダ <div data-id="ph-..."> を含む）
    - data_parts: 画像/添付の素材（PendingPart）
    """
    section_id: str
    page_title: str
    body_html: str
    data_parts: list[PendingPart] = field(default_factory=list)

    source_key: str | None = None




@dataclass(slots=True)
class Segment:
    segment_id: str          # data-id に使用
    kind: Literal["image", "attachment"]
    binary_part: BinaryPart  # 埋め込むバイナリデータ



# OneNoteページ作成時のバイナリパートデータモデル
@dataclass(frozen=True)
class BinaryPart:
    kind: Literal["image", "attachment"]
    filename: str
    content_type: str
    data: bytes
    origin_field: str
    width: int | None = None
    height: int | None = None





# OneNoteページ作成時のペイロードデータモデル
@dataclass(frozen=True)
class OneNoteCreatePagePayload:
    section_id: str
    page_title: str
    body_html: str
    parts: list[BinaryPart] = field(default_factory=list)




@dataclass(frozen=True)
class PendingPart:
    """変換段階の素材（name未確定）。送信段階で BinaryPart に変換する。"""
    placeholder_id: str             # data-id (ターゲット指定に使う)
    kind: Literal["image", "attachment"]
    filename: str
    content_type: str
    data: bytes
    origin_field: str               # どのDXLフィールド由来か（デバッグ用）
    width: int | None = None
    height: int | None = None
