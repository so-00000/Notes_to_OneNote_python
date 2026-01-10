# renderer_rich.py
from __future__ import annotations

import html
import re
from typing import Optional

from .models import OneNoteRow


# ========== small helpers ==========

def _esc(s: Optional[str]) -> str:
    """HTMLエスケープ（Noneは空文字）。"""
    return "" if s is None else html.escape(str(s))

def _nl2br(s: Optional[str]) -> str:
    """改行を<br/>に変換してHTMLエスケープ。"""
    if not s:
        return ""
    t = str(s).replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(t).replace("\n", "<br/>")

def _join_nonempty(*parts: Optional[str], sep: str = " ") -> str:
    """空文字を除外して結合。"""
    xs = [p.strip() for p in parts if p and str(p).strip()]
    return sep.join(xs)



def _normalize_notes_dt(s: Optional[str]) -> str:
    """Notesの日時表記を人間が読みやすい形に整形。"""
    if not s:
        return ""
    t = str(s).strip()

    # YYYYMMDD
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", t)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

    # T141700,00 (time only)  ※小数部は 0〜数桁 を許容
    m = re.fullmatch(r"T(\d{2})(\d{2})(\d{2})(?:,\d+)?(?:[+-]\d{2})?", t)
    if m:
        hh, mm, ss = m.group(1), m.group(2), m.group(3)
        return f"{hh}:{mm}:{ss}"

    # 20241031T154057,98+09 (datetime) ※小数部は 0〜数桁、TZは捨てる
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(?:,\d+)?(?:[+-]\d{2})?", t)
    if m:
        y, mo, d, hh, mm, ss = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        return f"{y}/{mo}/{d} {hh}:{mm}:{ss}"

    # どれでもない場合はそのまま返す（Noneにしない）
    return t


def _fmt_dt(date_s: Optional[str], time_s: Optional[str]) -> str:
    """
    time側に日付が入ってる（YYYYMMDDT...）場合は date側を無視して二重化を防ぐ。
    """
    t = (time_s or "").strip()
    if re.match(r"^\d{8}T", t):
        return _normalize_notes_dt(t)

    d = _normalize_notes_dt(date_s)
    tt = _normalize_notes_dt(time_s)
    return _join_nonempty(d, tt, sep=" ")



def _split_multi(s: Optional[str]) -> list[str]:
    """区切り文字で複数値に分割する（現在は未使用）。"""
    if not s:
        return []
    t = str(s).strip().replace("　", " ")
    parts = re.split(r"[;,/|]+|\s{2,}|\s", t)
    return [p for p in (x.strip() for x in parts) if p]


def _kv_row(k: str, v_html: str) -> str:
    """2カラムのテーブル行（左：キー／右：値HTML）。"""
    return (
        "<tr>"
        f"<td style='width:180px; background:#f5f5f5; border:1px solid #ddd; padding:6px; vertical-align:top;'><b>{_esc(k)}</b></td>"
        f"<td style='border:1px solid #ddd; padding:6px; vertical-align:top;'>{v_html}</td>"
        "</tr>"
    )

def _section_title(title: str) -> str:
    """セクションの見出し。"""
    return (
        "<div style='margin-top:16px; padding:8px 10px; background:#eef6ff; border:1px solid #cfe6ff;'>"
        f"<b>{_esc(title)}</b>"
        "</div>"
    )

def _as_html_or_text(s: Optional[str]) -> str:
    """HTML断片が来たらそのまま、そうでなければテキストとして改行変換。"""
    if not s:
        return ""
    t = str(s)
    if "<img" in t or "<p" in t or "<div" in t:
        return t
    return _nl2br(t)



# ========== main renderer ==========

def render_incident_like_page(note: OneNoteRow, *, source_file: str | None = None, row_no: int | None = None) -> str:
    """
    「システム管理」っぽいブロック構成でOneNote用HTML（<body>に入れる断片）を組み立てる。
    DXL→OneNoteRow版。
    """

    container_start = """
    <div style="
    max-width: 1100px;
    min-width: 900px;
    margin: 0 auto;
    padding: 8px;
    ">
    """

    # --- タイトル/識別
    management_no = note.DocumentNo or ""
    title_line = _join_nonempty("システム管理", "（移行）", sep=" ")

    # --- 承認系
    reporter1 = _join_nonempty(note.ReporterNm_1, f"({note.ReporterDep_1})" if note.ReporterDep_1 else None)
    approver1 = _join_nonempty(note.ApproverNm_1, f"({note.ApproverDep_1})" if note.ApproverDep_1 else None)
    reporter2 = _join_nonempty(note.ReporterNm_2, f"({note.ReporterDep_2})" if note.ReporterDep_2 else None)
    approver2 = _join_nonempty(note.ApproverNm_2, f"({note.ApproverDep_2})" if note.ApproverDep_2 else None)

    # --- 基本情報
    entry_user = _join_nonempty(note.EntryUser, note.EntryDept)
    syogai_ck_html = _nl2br(note.Syogai_ck)
    system_raw = note.System
    subsystem = note.SubSystem
    process_name = note.Task
    action_status = note.ActionStatus
    started = _fmt_dt(note.DocumentDate, note.DocumentTime)
    finished = _fmt_dt(note.ReplyDate, note.ReplyTime)
    work_time = note.WorkTime

    # --- 本文/件名
    subject_html = _as_html_or_text(note.Fd_Text_1 or note.DetailSubject or note.ReasonSubject)
    detail_html = _as_html_or_text(note.Detail)
    reason_html = _as_html_or_text(note.Reason)
    measure_memo_html = _as_html_or_text(note.Measure)

    # --- 影響範囲（元のロジック踏襲：Fd_Id_1 をそのまま表示）
    fd_id_1_html = _as_html_or_text(note.Fd_Id_1)

    # --- 暫定/恒久の本文
    # temp_text = _join_nonempty(note.Temporary, note.Temporary_Plan, note.Temporary_Comp, sep="\n")
    # perm_text = _join_nonempty(note.Parmanent, note.Parmanet_Plan, note.Parmanet_Comp, sep="\n")

    temp_html = _as_html_or_text(note.Temporary)
    perm_html = _as_html_or_text(note.Parmanent)


    # --- 添付（DXL由来の attachments があればそれを優先。従来の Fd_Link_1 / Fd_Text_1 も残す）
    attachments_li: list[str] = []

    # 1) DXL $FILE の添付名一覧（実ファイル添付はGraph送信側でやる想定）
    if getattr(note, "attachments", None):
        for fn in note.attachments:
            attachments_li.append(f"<li>{_esc(fn)}</li>")

    # 2) 既存のリンク/表示名（あれば）
    if note.Fd_Link_1:
        label = note.Fd_Text_1 or "Attachment"
        attachments_li.append(
            f"<li><a href='{html.escape(note.Fd_Link_1, quote=True)}'>{_esc(label)}</a></li>"
        )

    # 3) 参照ID（念のため）
    if note.Fd_Id_1:
        attachments_li.append(f"<li>Fd_Id_1: {_esc(note.Fd_Id_1)}</li>")

    attachments_html = "<ul>" + "".join(attachments_li) + "</ul>" if attachments_li else "<span style='color:#888;'>（なし）</span>"

    # --- Notesリンク（DXLの doclink を拾ってある前提：note.notes_links）
    notes_links_li: list[str] = []
    if getattr(note, "notes_links", None):
        for s in note.notes_links:
            # "desc | notesdoc:..." 形式を想定
            if "|" in s:
                desc, href = [x.strip() for x in s.split("|", 1)]
                notes_links_li.append(f"<li><a href='{_esc(href)}'>{_esc(desc)}</a></li>")
            else:
                notes_links_li.append(f"<li><a href='{_esc(s)}'>{_esc(s)}</a></li>")

    notes_links_html = "<ul>" + "".join(notes_links_li) + "</ul>" if notes_links_li else "<span style='color:#888;'>（なし）</span>"

    # --- ソース情報
    src_html = ""
    if source_file and row_no:
        src_html = (
            "<div style='margin-top:10px; color:#888; font-size:12px;'>"
            f"Source: {_esc(source_file)} / row {row_no}"
            "</div>"
        )

    # ===== assemble =====
    parts: list[str] = []

    # ヘッダー帯
    parts.append(
        "<div style='padding:10px; background:#d81b60; color:#fff; font-size:18px; font-weight:bold;'>"
        f"{_esc(title_line)}"
        "</div>"
    )

    # 承認経路 / 経過
    parts.append(_section_title("承認経路 / 経過"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row(
        "発生報告",
        _nl2br(_join_nonempty(reporter1, _normalize_notes_dt(note.ReportTime_1), sep="\n"))
    ))
    parts.append(_kv_row(
        "承認",
        _nl2br(_join_nonempty(approver1, _normalize_notes_dt(note.ApproveTime_1), note.ApproveStatus_1, sep="\n"))
    ))
    parts.append(_kv_row(
        "完了報告",
        _nl2br(_join_nonempty(reporter2, _normalize_notes_dt(note.ReportTime_2), sep="\n"))
    ))
    parts.append(_kv_row(
        "承認（完了）",
        _nl2br(_join_nonempty(approver2, _normalize_notes_dt(note.ApproveTime_2), note.ApproveStatus_2, sep="\n"))
    ))

    parts.append("</table>")

    parts.append(_section_title("管理番号"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("管理番号", f"<span style='font-size:16px; font-weight:bold;'>{_esc(management_no)}</span>"))
    parts.append("</table>")

    # 基本情報
    parts.append(_section_title("基本情報"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("入力者", _esc(entry_user)))
    parts.append(_kv_row("分類", syogai_ck_html))
    parts.append(_kv_row("システム", _esc(system_raw)))
    parts.append(_kv_row("サブシステム", _esc(subsystem)))
    parts.append(_kv_row("処理名", _esc(process_name)))
    parts.append(_kv_row("ステータス", _esc(action_status)))
    parts.append(_kv_row("開始日時", _esc(started)))
    parts.append(_kv_row("完了日時", _esc(finished)))
    parts.append(_kv_row("工数", _esc(work_time) + (" 分" if work_time else "")))
    parts.append("</table>")

    # 件名/内容
    parts.append(_section_title("件名 / 内容"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("件名", subject_html))
    parts.append(_kv_row("内容", detail_html))
    parts.append(_kv_row("理由・原因", reason_html))
    parts.append(_kv_row("対応（メモ）", measure_memo_html))
    parts.append("</table>")

    # # 件名/内容
    # parts.append(_section_title("件名"))
    # parts.append(subject_html)
    # parts.append(_section_title("内容"))
    # parts.append(detail_html)
    # parts.append(_section_title("理由・原因"))
    # parts.append(reason_html)
    # parts.append(_section_title("対応（メモ）"))
    # parts.append(measure_memo_html)


    # 分析
    parts.append(_section_title("分析"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("影響範囲", fd_id_1_html))

    parts.append(_kv_row("暫定策", _nl2br(temp_html)))
    parts.append(_kv_row("暫定策予定日付", _esc(note.Temporary_Plan)))
    parts.append(_kv_row("暫定策完了日付", _esc(note.Temporary_Comp)))

    parts.append(_kv_row("恒久策", _nl2br(perm_html)))
    parts.append(_kv_row("恒久策予定日付", _esc(note.Parmanet_Plan)))
    parts.append(_kv_row("恒久策完了日付", _esc(note.Parmanet_Comp)))

    parts.append(_kv_row("添付", attachments_html))
    parts.append(_kv_row("Notesリンク", notes_links_html))
    parts.append(_kv_row("予定日付", _esc(note.Temporary_Plan)))
    parts.append(_kv_row("完了日付", _esc(note.Temporary_Comp)))
    parts.append("</table>")

    parts.append(src_html)

    container_end = "</div>"
    return container_start + "\n".join(parts) + container_end
