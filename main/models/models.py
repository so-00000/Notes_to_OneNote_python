from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal


# =========================
#　処理全体の設定
# =========================

@dataclass(frozen=True)
class AppSettings:
    access_token: str   # Graph API 呼び出しに使うアクセストークン
    notebook_name: str  # 対象の OneNote ノートブック名
    section_name: str   # 対象の OneNote セクション名
    view_name: str      # 現在のデータ種別に対応するビュー名
    dxl_dir: Path       # 読み込み対象 DXL ディレクトリの絶対パス
    sleep_sec: float    # 連続登校時の待機時間


# =========================
#　対象データ毎の設定
# =========================
@dataclass(frozen=True)
class DataTypeSettings:
    label: str              # データ種別の表示名
    section_name: str       # 対象の OneNote セクション名
    view_name: str          # mapping/doc_mapping で使うビュー名
    dxl_dir: str            # 元データの DXL ディレクトリへの相対パス
    template_html_path: str # テンプレート HTML への相対パス
    fields_json_path: str   # フィールド定義 JSON への相対パス
    title_field: tuple[str, ...] | str  # ページタイトル生成に使う項目


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
