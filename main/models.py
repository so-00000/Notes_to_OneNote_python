from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from .dxl_attachments import DxlAttachment


@dataclass(frozen=True)
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


# OneNoteページ作成時のバイナリパートデータモデル
@dataclass(frozen=True)
class BinaryPart:
    # multipart の「データ部分」1つ
    name: str          # multipart のキー。HTML の name:参照にも使う（例: "img1"）
    filename: str      # 送信するファイル名（例: "a.png" / "b.xlsx"）
    content_type: str  # MIME（例: "image/png"）
    data: bytes        # バイナリ
    origin_field: str  # 元のDXLフィールド名など（デバッグ用



# OneNoteページ作成時のペイロードデータモデル
@dataclass(frozen=True)
class OneNoteCreatePagePayload:
    section_id: str
    page_title: str
    body_html: str
    parts: list[BinaryPart] = field(default_factory=list)