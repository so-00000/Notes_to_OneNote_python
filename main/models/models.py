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
    doc_replicaid: str | None = None
    doc_unid: str | None = None
    extracted_fields: dict[str, str] = field(default_factory=dict)
    doclink_placeholders: List[DocLinkPlaceholder] = field(default_factory=list)



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



@dataclass(frozen=True)
class DocLinkPlaceholder:
    """Notes doclink placeholder info for post-create patching."""
    placeholder_id: str
    target_replicaid: str
    target_unid: str
    label: str | None = None
