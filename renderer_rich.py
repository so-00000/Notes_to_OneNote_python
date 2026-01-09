# renderer_rich.py
from __future__ import annotations

import html
import re
from typing import Optional

from models import NoteRow


# ========== small helpers ==========

def _esc(s: Optional[str]) -> str:
    return "" if s is None else html.escape(str(s))

def _nl2br(s: Optional[str]) -> str:
    if not s:
        return ""
    t = str(s).replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(t).replace("\n", "<br/>")

def _join_nonempty(*parts: Optional[str], sep: str = " ") -> str:
    xs = [p.strip() for p in parts if p and str(p).strip()]
    return sep.join(xs)

def _fmt_dt(date_s: Optional[str], time_s: Optional[str]) -> str:
    # CSVの値が "2024/10/29" と "17:00" のように来る想定で単純に結合
    return _join_nonempty(date_s, time_s, sep=" ")

def _split_multi(s: Optional[str]) -> list[str]:
    """
    システムや影響範囲が複数選択のとき用の雑分割
    （CSV側が「フード NCB」や「フード;NCB」などでもある程度拾う）
    """
    if not s:
        return []
    t = str(s).strip()
    # 全角スペースも区切り扱い
    t = t.replace("　", " ")
    parts = re.split(r"[;,/|]+|\s{2,}|\s", t)
    return [p for p in (x.strip() for x in parts) if p]

def _checkbox(label: str, checked: bool) -> str:
    # OneNoteは input[type=checkbox] が怪しいことがあるので記号で表現
    mark = "■" if checked else "□"
    return f"<span style='margin-right:10px; white-space:nowrap;'>{mark} {_esc(label)}</span>"

def _kv_row(k: str, v_html: str) -> str:
    return (
        "<tr>"
        f"<td style='width:180px; background:#f5f5f5; border:1px solid #ddd; padding:6px; vertical-align:top;'><b>{_esc(k)}</b></td>"
        f"<td style='border:1px solid #ddd; padding:6px; vertical-align:top;'>{v_html}</td>"
        "</tr>"
    )

def _section_title(title: str) -> str:
    return (
        "<div style='margin-top:16px; padding:8px 10px; background:#eef6ff; border:1px solid #cfe6ff;'>"
        f"<b>{_esc(title)}</b>"
        "</div>"
    )


# ========== main renderer ==========

def render_incident_like_page(note: NoteRow, *, source_file: str | None = None, row_no: int | None = None) -> str:
    """
    PDF「システム管理」画面っぽいブロック構成でHTMLを組み立てる。
    - OneNoteにPOSTする時は <body> にそのまま入れればOK
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

    # --- 承認系（CSVに値があれば出す）
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
    # subject = note.DetailSubject or note.ReasonSubject or note.Ask
    fd_text_1_html = _nl2br(note.Fd_Text_1)
    detail_html = _nl2br(note.Detail)
    reason_html = _nl2br(note.Reason)
    measure_html = _nl2br(note.Measure)

    # --- 影響範囲（PDFに出てくる候補の並びを固定で持つ）
    fd_id_1_html = _nl2br(note.Fd_Id_1)
    # --- 対応区分（暫定/恒久）
    measure_html = _nl2br(note.Measure)

    # --- 暫定/恒久の本文
    temp_block = _join_nonempty(note.Temporary, note.Temporary_Plan, note.Temporary_Comp, sep="<br/>")
    perm_block = _join_nonempty(note.Parmanent, note.Parmanet_Plan, note.Parmanet_Comp, sep="<br/>")

    # --- 添付（CSVにリンク/IDがあれば表示だけする。実ファイルは今は無い想定）
    attachments = []
    if note.Fd_Link_1:
        # リンクとして扱えるなら aタグ。無理ならテキスト表示でもOK
        attachments.append(f"<li><a href='{html.escape(note.Fd_Link_1, quote=True)}'>{_esc(note.Fd_Text_1 or 'Attachment')}</a></li>")
    elif note.Fd_Text_1:
        attachments.append(f"<li>{_esc(note.Fd_Text_1)}</li>")
    if note.Fd_Id_1:
        attachments.append(f"<li>Fd_Id_1: {_esc(note.Fd_Id_1)}</li>")
    attachments_html = "<ul>" + "".join(attachments) + "</ul>" if attachments else "<span style='color:#888;'>（なし）</span>"

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

    # ヘッダー帯（PDFの赤帯をイメージ） :contentReference[oaicite:2]{index=2}
    parts.append(
        "<div style='padding:10px; background:#d81b60; color:#fff; font-size:18px; font-weight:bold;'>"
        f"{_esc(title_line)}"
        "</div>"
    )

    # 承認経路（あれば出す：PDF上部のブロック） :contentReference[oaicite:3]{index=3}
    parts.append(_section_title("承認経路 / 経過"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("発生報告", _nl2br(_join_nonempty(reporter1, note.ReportTime_1, sep="\n"))))
    parts.append(_kv_row("承認", _nl2br(_join_nonempty(approver1, note.ApproveTime_1, note.ApproveStatus_1, sep="\n"))))
    parts.append(_kv_row("完了報告", _nl2br(_join_nonempty(reporter2, note.ReportTime_2, sep="\n"))))
    parts.append(_kv_row("承認（完了）", _nl2br(_join_nonempty(approver2, note.ApproveTime_2, note.ApproveStatus_2, sep="\n"))))
    parts.append("</table>")

    parts.append(_section_title("管理番号"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("管理番号", f"<span style='font-size:16px; font-weight:bold;'>{_esc(management_no)}</span>"))
    parts.append("</table>")

    # 基本情報（管理番号など） :contentReference[oaicite:4]{index=4}
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

    # 件名/内容（PDFの下部テキストエリア） 
    parts.append(_section_title("件名 / 内容"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("件名", fd_text_1_html))
    parts.append(_kv_row("内容", detail_html))
    parts.append(_kv_row("理由・原因", reason_html))
    parts.append(_kv_row("対応（メモ）", measure_html))
    parts.append("</table>")

    # 分析（影響範囲/対応区分/暫定策/添付/予定日付…） :contentReference[oaicite:6]{index=6}
    parts.append(_section_title("分析"))
    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("影響範囲", fd_id_1_html))
    parts.append(_kv_row("対応区分", measure_html))
    parts.append(_kv_row("暫定策", _nl2br(temp_block)))
    parts.append(_kv_row("恒久策", _nl2br(perm_block)))
    parts.append(_kv_row("添付（参照のみ）", attachments_html))
    parts.append(_kv_row("予定日付", _esc(note.Temporary_Plan)))
    parts.append(_kv_row("完了日付", _esc(note.Temporary_Comp)))
    parts.append("</table>")

    parts.append(src_html)

    container_end = "</div>"
    return container_start + "\n".join(parts) + container_end
