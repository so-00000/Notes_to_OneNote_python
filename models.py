# models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


def _get(row: Dict[str, Any], key: str) -> Optional[str]:
    """CSV DictReader の row から文字列を安全に取得する（空は None）。"""
    v = row.get(key, None)
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


@dataclass(frozen=True)
class NoteRow:
    # --- そのまま使える英数字/アンダースコア列 ---
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

    # --- Pythonの識別子にできない列（日本語・$含む） ---
    office_master_id: Optional[str] = field(default=None, metadata={"csv": "事業所マスタID"})
    occurred_ym: Optional[str] = field(default=None, metadata={"csv": "発生年月"})
    revisions: Optional[str] = field(default=None, metadata={"csv": "$Revisions"})

    @staticmethod
    def from_csv_row(row: Dict[str, Any]) -> "NoteRow":
        """csv.DictReader の1行(dict)から NoteRow を生成する。"""
        return NoteRow(
            SAVEFLAG=_get(row, "SAVEFLAG"),
            Form=_get(row, "Form"),
            Author=_get(row, "Author"),
            DelFlg=_get(row, "DelFlg"),
            Status=_get(row, "Status"),
            ApplicantRole=_get(row, "ApplicantRole"),
            Step1=_get(row, "Step1"),
            ReporterNm_1=_get(row, "ReporterNm_1"),
            ReporterDep_1=_get(row, "ReporterDep_1"),
            ReportTime_1=_get(row, "ReportTime_1"),
            ApproverNm_1=_get(row, "ApproverNm_1"),
            ApproveStatus_1=_get(row, "ApproveStatus_1"),
            ApproverDep_1=_get(row, "ApproverDep_1"),
            ApproveTime_1=_get(row, "ApproveTime_1"),
            ReporterNm_2=_get(row, "ReporterNm_2"),
            ReporterDep_2=_get(row, "ReporterDep_2"),
            ReportTime_2=_get(row, "ReportTime_2"),
            ApproverNm_2=_get(row, "ApproverNm_2"),
            ApproveStatus_2=_get(row, "ApproveStatus_2"),
            ApproverDep_2=_get(row, "ApproverDep_2"),
            ApproveTime_2=_get(row, "ApproveTime_2"),
            DocumentNo=_get(row, "DocumentNo"),
            EntryUser=_get(row, "EntryUser"),
            EntryDept=_get(row, "EntryDept"),
            Ask=_get(row, "Ask"),
            AskUser=_get(row, "AskUser"),
            Syogai_ck=_get(row, "Syogai_ck"),
            System=_get(row, "System"),
            SubSystem=_get(row, "SubSystem"),
            Task=_get(row, "Task"),
            ActionStatus=_get(row, "ActionStatus"),
            DocumentDate=_get(row, "DocumentDate"),
            DocumentTime=_get(row, "DocumentTime"),
            ReplyDate=_get(row, "ReplyDate"),
            ReplyTime=_get(row, "ReplyTime"),
            WorkTime=_get(row, "WorkTime"),
            Detail=_get(row, "Detail"),
            Reason=_get(row, "Reason"),
            Detail_1=_get(row, "Detail_1"),
            Fd_Link_1=_get(row, "Fd_Link_1"),
            Fd_Id_1=_get(row, "Fd_Id_1"),
            Measure=_get(row, "Measure"),
            Temporary=_get(row, "Temporary"),
            Temporary_Plan=_get(row, "Temporary_Plan"),
            Temporary_Comp=_get(row, "Temporary_Comp"),
            Parmanent=_get(row, "Parmanent"),
            Parmanet_Plan=_get(row, "Parmanet_Plan"),
            Parmanet_Comp=_get(row, "Parmanet_Comp"),
            Agenda_Text=_get(row, "Agenda_Text"),
            Agenda=_get(row, "Agenda"),
            Leaders_1=_get(row, "Leaders_1"),
            Leaders_2=_get(row, "Leaders_2"),
            Leaders_3=_get(row, "Leaders_3"),
            Leaders_4=_get(row, "Leaders_4"),
            Leaders_5=_get(row, "Leaders_5"),
            Directors_1=_get(row, "Directors_1"),
            Directors_2=_get(row, "Directors_2"),
            Directors_3=_get(row, "Directors_3"),
            Directors_4=_get(row, "Directors_4"),
            Directors_5=_get(row, "Directors_5"),
            Agents_1=_get(row, "Agents_1"),
            Agents_2=_get(row, "Agents_2"),
            Agents_3=_get(row, "Agents_3"),
            Agents_4=_get(row, "Agents_4"),
            Agents_5=_get(row, "Agents_5"),
            ApplicantUser=_get(row, "ApplicantUser"),
            ApproverRole=_get(row, "ApproverRole"),
            ApproverUser=_get(row, "ApproverUser"),
            AgentRole=_get(row, "AgentRole"),
            AgentUser=_get(row, "AgentUser"),
            Step2=_get(row, "Step2"),
            Division=_get(row, "Division"),
            No_Category=_get(row, "No_Category"),
            No_Num=_get(row, "No_Num"),
            Fd_Text_1=_get(row, "Fd_Text_1"),
            DetailSubject=_get(row, "DetailSubject"),
            ReasonSubject=_get(row, "ReasonSubject"),
            office_master_id=_get(row, "事業所マスタID"),
            occurred_ym=_get(row, "発生年月"),
            revisions=_get(row, "$Revisions"),
        )
