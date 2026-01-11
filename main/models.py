from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from .dxl_attachments import DxlAttachment
from typing import Literal


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




@dataclass
class OneNoteRow:
    # ---- 固定フィールド
    SAVEFLAG: Optional[str] = None
    Form: Optional[str] = None
    Author: Optional[str] = None
    DelFlg: Optional[str] = None
    Status: Optional[str] = None
    ApplicantRole: Optional[str] = None
    Step1: Optional[str] = None
    ReporterNm_1: Optional[str] = None
    ReporterDep_1: Optional[str] = None
    ReportTime_1: Optional[str] = None
    ApproverNm_1: Optional[str] = None
    ApproveStatus_1: Optional[str] = None
    ApproverDep_1: Optional[str] = None
    ApproveTime_1: Optional[str] = None
    ReporterNm_2: Optional[str] = None
    ReporterDep_2: Optional[str] = None
    ReportTime_2: Optional[str] = None
    ApproverNm_2: Optional[str] = None
    ApproveStatus_2: Optional[str] = None
    ApproverDep_2: Optional[str] = None
    ApproveTime_2: Optional[str] = None
    DocumentNo: Optional[str] = None
    EntryUser: Optional[str] = None
    EntryDept: Optional[str] = None
    Ask: Optional[str] = None
    AskUser: Optional[str] = None
    Syogai_ck: Optional[str] = None
    System: Optional[str] = None
    SubSystem: Optional[str] = None
    Task: Optional[str] = None
    ActionStatus: Optional[str] = None
    DocumentDate: Optional[str] = None
    DocumentTime: Optional[str] = None
    ReplyDate: Optional[str] = None
    ReplyTime: Optional[str] = None
    WorkTime: Optional[str] = None
    Detail: Optional[str] = None
    Reason: Optional[str] = None
    Detail_1: Optional[str] = None
    Fd_Link_1: Optional[str] = None
    Fd_Id_1: Optional[str] = None
    Measure: Optional[str] = None
    Temporary: Optional[str] = None
    Temporary_Plan: Optional[str] = None
    Temporary_Comp: Optional[str] = None
    Parmanent: Optional[str] = None
    Parmanet_Plan: Optional[str] = None
    Parmanet_Comp: Optional[str] = None
    Agenda_Text: Optional[str] = None
    Agenda: Optional[str] = None
    Leaders_1: Optional[str] = None
    Leaders_2: Optional[str] = None
    Leaders_3: Optional[str] = None
    Leaders_4: Optional[str] = None
    Leaders_5: Optional[str] = None
    Directors_1: Optional[str] = None
    Directors_2: Optional[str] = None
    Directors_3: Optional[str] = None
    Directors_4: Optional[str] = None
    Directors_5: Optional[str] = None
    Agents_1: Optional[str] = None
    Agents_2: Optional[str] = None
    Agents_3: Optional[str] = None
    Agents_4: Optional[str] = None
    Agents_5: Optional[str] = None
    ApplicantUser: Optional[str] = None
    ApproverRole: Optional[str] = None
    ApproverUser: Optional[str] = None
    AgentRole: Optional[str] = None
    AgentUser: Optional[str] = None
    Step2: Optional[str] = None
    Division: Optional[str] = None
    No_Category: Optional[str] = None
    No_Num: Optional[str] = None
    Fd_Text_1: Optional[str] = None
    DetailSubject: Optional[str] = None
    ReasonSubject: Optional[str] = None

    # 上記以外のフィールド出現時対応
    extra: Dict[str, str] = field(default_factory=dict)

    # OneNote化で使用
    attachments: List[str] = field(default_factory=list)         # 表示/参照用
    attachment_objs: List[DxlAttachment] = field(default_factory=list)  # 送信用（本体）
    notes_links: List[str] = field(default_factory=list)  # doclink等を仮リンク文字列で保持



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
