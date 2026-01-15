# render_syogai_db_html.py
from __future__ import annotations

from main.models.SyogaiDb import SyogaiDbRaw
from main.services.util_render import (
    _esc,
    _fmt_dt,
    _join_nonempty,
    _kv_row,
    _nl2br,
    _normalize_notes_dt,
    add_text_block,
    add_title,
)


def render_syogai_db_html(
    note: SyogaiDbRaw,
    *,
    source_file: str | None = None,
    row_no: int | None = None
) -> str:
    container_start = "<div style='max-width:1100px; min-width:900px; margin:0 auto; padding:8px;'>"
    parts: list[str] = []

    def add_section_title(title: str) -> None:
        add_title(parts, title)

    def add_section_text_block(s: str | None) -> None:
        add_text_block(parts, s)

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
    add_section_title("管理番号")
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("管理番号", f"<span style='font-size:16px; font-weight:bold;'>{_esc(note.DocumentNo)}</span>"))
    parts.append("</table>")

    # --- 基本情報 ---
    add_section_title("基本情報")
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
    add_section_title("件名 / 内容")
    add_section_title("件名")
    add_section_text_block(note.Fd_Text_1)

    add_section_title("内容")
    parts.append(note.Detail)

    add_section_title("理由・原因")
    parts.append(note.Reason)

    add_section_title("対応（メモ）")
    add_section_text_block(note.Measure)

    # --- 分析 ---
    add_section_title("分析")
    add_section_title("影響範囲")
    add_section_text_block(note.Fd_Id_1)

    add_section_title("暫定策")
    parts.append(note.Temporary)
    add_section_title("暫定策予定日付")
    add_section_text_block(note.Temporary_Plan)
    add_section_title("暫定策完了日付")
    add_section_text_block(note.Temporary_Comp)

    add_section_title("恒久策")
    parts.append(note.Parmanent)
    add_section_title("恒久策予定日付")
    add_section_text_block(note.Parmanet_Plan)
    add_section_title("恒久策完了日付")
    add_section_text_block(note.Parmanet_Comp)

    # --- Notesリンク ---
    add_section_title("Notesリンク")
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
