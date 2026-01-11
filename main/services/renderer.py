# renderer.py
from __future__ import annotations

import html
import re
from typing import Optional

from .models import OneNoteRow


def _nl2br(s: Optional[str]) -> str:
    """プレーンテキストを安全に表示（escape + 改行を<br/>）。"""
    if not s:
        return ""
    t = str(s).replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(t).replace("\n", "<br/>")


def _esc(s: Optional[str]) -> str:
    """単発テキスト（改行不要）をescape。"""
    return "" if s is None else html.escape(str(s))


def _join_nonempty(*parts: Optional[str], sep: str = " ") -> str:
    """空文字を除外して結合"""
    xs = [str(p).strip() for p in parts if p is not None and str(p).strip()]
    return sep.join(xs)


def _normalize_notes_dt(s: Optional[str]) -> str:
    """Notesの日時表記を人間が読みやすい形に整形。"""
    if not s:
        return ""
    t = str(s).strip()

    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", t)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

    m = re.fullmatch(r"T(\d{2})(\d{2})(\d{2})(?:,\d+)?(?:[+-]\d{2})?", t)
    if m:
        return f"{m.group(1)}:{m.group(2)}:{m.group(3)}"

    m = re.fullmatch(
        r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(?:,\d+)?(?:[+-]\d{2})?", t
    )
    if m:
        y, mo, d, hh, mm, ss = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        return f"{y}/{mo}/{d} {hh}:{mm}:{ss}"

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


def render_to_html_body(
    note: OneNoteRow,
    *,
    source_file: str | None = None,
    row_no: int | None = None
) -> str:
    container_start = "<div style='max-width:1100px; min-width:900px; margin:0 auto; padding:8px;'>"
    parts: list[str] = []

    def add_title(title: str) -> None:
        parts.append(_section_title(title))

    def add_text_block(s: Optional[str]) -> None:
        parts.append(f"<p>{_nl2br(s) or '<br/>'}</p>")


    # --- 承認経路 ---
    reporter1 = _join_nonempty(note.ReporterNm_1, note.ReporterDep_1)
    approver1 = _join_nonempty(note.ApproverNm_1, note.ApproverDep_1)
    reporter2 = _join_nonempty(note.ReporterNm_2, note.ReporterDep_2)
    approver2 = _join_nonempty(note.ApproverNm_2, note.ApproverDep_2)

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("発生報告", _nl2br(_join_nonempty(reporter1, _normalize_notes_dt(note.ReportTime_1), sep="\n"))))
    parts.append(_kv_row("承認", _nl2br(_join_nonempty(approver1, _normalize_notes_dt(note.ApproveTime_1), note.ApproveStatus_1, sep="\n"))))
    parts.append(_kv_row("完了報告", _nl2br(_join_nonempty(reporter2, _normalize_notes_dt(note.ReportTime_2), sep="\n"))))
    parts.append(_kv_row("承認（完了）", _nl2br(_join_nonempty(approver2, _normalize_notes_dt(note.ApproveTime_2), note.ApproveStatus_2, sep="\n"))))
    parts.append("</table>")

    # --- 管理番号 ---
    add_title("管理番号")
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("管理番号", f"<span style='font-size:16px; font-weight:bold;'>{_esc(note.DocumentNo)}</span>"))
    parts.append("</table>")

    # --- 基本情報 ---
    add_title("基本情報")
    entry_user = _join_nonempty(note.EntryUser, note.EntryDept)
    started = _fmt_dt(note.DocumentDate, note.DocumentTime)
    finished = _fmt_dt(note.ReplyDate, note.ReplyTime)
    work_time = (note.WorkTime or "").strip()

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("入力者", _esc(entry_user)))
    parts.append(_kv_row("分類", _nl2br(note.Syogai_ck)))
    parts.append(_kv_row("システム", _esc(note.System)))
    parts.append(_kv_row("サブシステム", _esc(note.SubSystem)))
    parts.append(_kv_row("処理名", _esc(note.Task)))
    parts.append(_kv_row("ステータス", _esc(note.ActionStatus)))
    parts.append(_kv_row("開始日時", _esc(started)))
    parts.append(_kv_row("完了日時", _esc(finished)))
    parts.append(_kv_row("工数", _esc(work_time) + (" 分" if work_time else "")))
    parts.append("</table>")

    # --- 件名 / 内容 ---
    add_title("件名 / 内容")
    add_title("件名")
    add_text_block(note.Fd_Text_1)

    add_title("内容")
    parts.append(note.Detail)

    add_title("理由・原因")
    note.Reason

    add_title("対応（メモ）")
    add_text_block(note.Measure)

    # --- 分析 ---
    add_title("分析")
    add_title("影響範囲")
    add_text_block(note.Fd_Id_1)

    add_title("暫定策")
    parts.append(note.Temporary)
    add_title("暫定策予定日付")
    add_text_block(note.Temporary_Plan)
    add_title("暫定策完了日付")
    add_text_block(note.Temporary_Comp)

    add_title("恒久策")
    parts.append(note.Parmanent)
    add_title("恒久策予定日付")
    add_text_block(note.Parmanet_Plan)
    add_title("恒久策完了日付")
    add_text_block(note.Parmanet_Comp)

    # --- Notesリンク ---
    add_title("Notesリンク")
    notes_links_li: list[str] = []
    for s in (getattr(note, "notes_links", None) or []):
        if "|" in s:
            desc, href = [x.strip() for x in s.split("|", 1)]
            notes_links_li.append(f"<li><a href='{_esc(href)}'>{_esc(desc)}</a></li>")
        else:
            notes_links_li.append(f"<li><a href='{_esc(s)}'>{_esc(s)}</a></li>")
    parts.append("<ul>" + "".join(notes_links_li) + "</ul>" if notes_links_li else "<span style='color:#888;'>（なし）</span>")

    # --- ソース情報 ---
    if source_file is not None and row_no is not None:
        parts.append(
            "<div style='margin-top:10px; color:#888; font-size:12px;'>"
            f"Source: {_esc(source_file)} / row {row_no}"
            "</div>"
        )

    return container_start + "\n".join(parts) + "</div>"