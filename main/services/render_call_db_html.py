# render_call_db_html.py
from __future__ import annotations

from typing import Optional

from main.models.CallDb import CallDbRaw
from main.services.util_render import (
    _esc,
    _fmt_dt,
    _join_nonempty,
    _kv_row,
    _nl2br,
    _normalize_notes_dt,
    _section_title,
)


def render_call_db_html(
    note: CallDbRaw,
    *,
    source_file: str | None = None,
    row_no: int | None = None,
) -> str:
    container_start = "<div style='max-width:1100px; min-width:900px; margin:0 auto; padding:8px;'>"
    parts: list[str] = []

    def add_title(title: str) -> None:
        parts.append(_section_title(title))

    def add_text_block(s: Optional[str]) -> None:
        parts.append(f"<p>{_nl2br(s) or '<br/>'}</p>")

    def add_html_block(s: Optional[str]) -> None:
        parts.append(s or "<p><br/></p>")

    # --- 承認経路（あれば表示） ---
    reporter1 = _join_nonempty(note.ReporterNm_1, note.ReporterDep_1)
    approver1 = _join_nonempty(note.ApproverNm_1, note.ApproverDep_1)
    reporter2 = _join_nonempty(note.ReporterNm_2, note.ReporterDep_2)
    approver2 = _join_nonempty(note.ApproverNm_2, note.ApproverDep_2)
    has_approval = any(
        [
            reporter1,
            approver1,
            reporter2,
            approver2,
            note.ReportTime_1,
            note.ReportTime_2,
            note.ApproveTime_1,
            note.ApproveTime_2,
        ]
    )
    if has_approval:
        parts.append("<table style='width:100%; border-collapse:collapse;'>")
        parts.append(
            _kv_row(
                "発生報告",
                _nl2br(_join_nonempty(reporter1, _normalize_notes_dt(note.ReportTime_1), sep="\n")),
            )
        )
        parts.append(
            _kv_row(
                "承認",
                _nl2br(
                    _join_nonempty(
                        approver1, _normalize_notes_dt(note.ApproveTime_1), note.ApproveStatus_1, sep="\n"
                    )
                ),
            )
        )
        parts.append(
            _kv_row(
                "完了報告",
                _nl2br(_join_nonempty(reporter2, _normalize_notes_dt(note.ReportTime_2), sep="\n")),
            )
        )
        parts.append(
            _kv_row(
                "承認（完了）",
                _nl2br(
                    _join_nonempty(
                        approver2, _normalize_notes_dt(note.ApproveTime_2), note.ApproveStatus_2, sep="\n"
                    )
                ),
            )
        )
        parts.append("</table>")

    # --- 管理番号 ---
    add_title("管理番号")
    management_no = _join_nonempty(note.mng_no, note.DocumentNo)
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(
        _kv_row("管理番号", f"<span style='font-size:16px; font-weight:bold;'>{_esc(management_no)}</span>")
    )
    parts.append("</table>")

    # --- 基本情報 ---
    add_title("基本情報")
    entry_user = _join_nonempty(note.EntryUser, note.EntryDept)
    created = _fmt_dt(note.DocumentDate, note.DocumentTime)
    closed = _fmt_dt(note.ReplyDate, note.ReplyTime)
    created_alt = _normalize_notes_dt(note.CreateDateTime)
    closed_alt = _normalize_notes_dt(note.CloseDateTime)
    status = _join_nonempty(note.status, note.ActionStatus, note.Status)
    category = _join_nonempty(
        note.category1,
        note.category2,
        note.category3,
        note.category4,
        note.category5,
        sep=" / ",
    )
    work_time = (note.WorkTime or "").strip()

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("入力者", _esc(entry_user)))
    parts.append(_kv_row("ステータス", _esc(status)))
    parts.append(_kv_row("カテゴリ", _esc(category)))
    parts.append(_kv_row("システム", _esc(note.System)))
    parts.append(_kv_row("サブシステム", _esc(note.SubSystem)))
    parts.append(_kv_row("処理名", _esc(note.Task)))
    parts.append(_kv_row("作成日時", _esc(_join_nonempty(created, created_alt))))
    parts.append(_kv_row("完了日時", _esc(_join_nonempty(closed, closed_alt))))
    parts.append(_kv_row("工数", _esc(work_time) + (" 分" if work_time else "")))
    parts.append("</table>")

    # --- 顧客情報 ---
    add_title("顧客情報")
    customer_name = _join_nonempty(note.customername, note.customername_1, note.customername_2)
    customer_company = _join_nonempty(note.KAISHA, note.customercompanycd)
    contact_tel = _join_nonempty(note.tel, note.mobile_tel_no)
    contact_address = _join_nonempty(note.MailAddress, note.mailitem)

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("顧客名", _esc(customer_name)))
    parts.append(_kv_row("会社", _esc(customer_company)))
    parts.append(_kv_row("顧客番号", _esc(_join_nonempty(note.customerno, note.customerID))))
    parts.append(_kv_row("連絡先", _esc(contact_tel)))
    parts.append(_kv_row("メール", _esc(contact_address)))
    parts.append("</table>")

    # --- 件名 / 内容 ---
    add_title("件名 / 内容")
    add_title("件名")
    add_text_block(_join_nonempty(note.outline, note.Title))

    add_title("問い合わせ内容")
    add_text_block(_join_nonempty(note.inquiry, note.Ask))

    add_title("詳細")
    add_html_block(note.Detail or note.body)

    add_title("詳細（追記）")
    add_html_block(note.Detail_1 or note.body_1)

    add_title("原因・理由")
    add_text_block(_join_nonempty(note.genin, note.Reason))

    add_title("対応内容")
    add_text_block(_join_nonempty(note.answer, note.TAIOU, note.Measure))

    add_title("備考")
    add_text_block(_join_nonempty(note.BIKOU, note.Memo))

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
