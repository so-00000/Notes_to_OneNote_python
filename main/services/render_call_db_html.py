# render_call_db_html.py
from __future__ import annotations

from typing import Optional

from main.models.CallDb import CallDbRaw
from main.services.util_render import (
    _esc,
    _join_nonempty,
    _kv_row,
    _nl2br,
    _section_title,
)


def render_call_db_html(
    note: CallDbRaw,
    *,
    source_file: str | None = None,
    row_no: int | None = None,
) -> str:
    """
    CallDB（CallDbRaw）をOneNote向けHTML（1ページ）にレンダリングする。

    - PDFが複数ページでも、OneNote上は1ページに縦並びで収める（セクションで区切る）。
    - 表示ラベルはPDF寄せの論理名（日本語）を使用する。
    - 問合せ発生/対応開始は画面定義に合わせて SDATE/STIME と TDATE/TTIME を採用。
    - ユーザー番号＝customerID、問合せ者ユーザーID＝pass_1 を採用。
    - rich_fields（body等）はHTMLとしてそのまま差し込む（空なら出さない）。
    - PDFの注意文（固定文言）は表示しない。
    """

    container_start = (
        "<div style='max-width:1100px; min-width:900px; margin:0 auto; padding:8px;'>"
    )
    parts: list[str] = []

    def add_title(title: str) -> None:
        parts.append(_section_title(title))

    def add_text_row(label: str, s: Optional[str]) -> None:
        parts.append(_kv_row(_esc(label), f"<p>{_nl2br(s) or '<br/>'}</p>"))

    def add_html_row(label: str, html: Optional[str]) -> None:
        if (html or "").strip():
            parts.append(_kv_row(_esc(label), html))

    def _looks_like_html(value: Optional[str]) -> bool:
        if not value:
            return False
        return "<" in str(value) and ">" in str(value)

    def add_rich_row(label: str, value: Optional[str]) -> None:
        if not (value or "").strip():
            parts.append(_kv_row(_esc(label), "<p><br/></p>"))
            return
        if _looks_like_html(value):
            parts.append(_kv_row(_esc(label), str(value)))
            return
        parts.append(_kv_row(_esc(label), f"<p>{_nl2br(value) or '<br/>'}</p>"))

    def _pick_first(*vals: Optional[str]) -> Optional[str]:
        for v in vals:
            if v is None:
                continue
            if str(v).strip():
                return v
        return None

    def _compose_dt(
        y: Optional[str],
        m: Optional[str],
        d: Optional[str],
        hh: Optional[str],
        mm: Optional[str],
    ) -> str:
        """
        SDATE/TDATE + STIME/TTIME のような分割フィールドを "YYYY/MM/DD HH:MM" に整形。
        欠けがあれば可能な範囲で結合し、空なら空文字。
        """
        yy = (y or "").strip()
        mo = (m or "").strip()
        dd = (d or "").strip()
        h = (hh or "").strip()
        mi = (mm or "").strip()

        date = ""
        if yy and mo and dd:
            date = f"{yy}/{mo.zfill(2)}/{dd.zfill(2)}"
        elif yy or mo or dd:
            date = "/".join(
                [
                    x
                    for x in [
                        yy,
                        mo.zfill(2) if mo else "",
                        dd.zfill(2) if dd else "",
                    ]
                    if x
                ]
            )

        time = ""
        if h and mi:
            time = f"{h.zfill(2)}:{mi.zfill(2)}"
        elif h:
            time = f"{h.zfill(2)}"
        elif mi:
            time = f"{mi.zfill(2)}"

        return _join_nonempty(date, time, sep=" ")

    # =========================
    # 0) ヘッダー（1ページ内の見出し）
    # =========================
    # OneNoteページタイトル自体は title_fields で別途付く想定だが、
    # HTML内にも読みやすい見出しとして出す。
    headline = _join_nonempty(note.mng_no, note.outline, sep="  /  ")
    parts.append(
        "<div style='font-size:18px; font-weight:bold; margin:4px 0 10px;'>"
        f"{_esc(headline) if headline else 'CallDB'}"
        "</div>"
    )

    # =========================
    # 1) 一次対応（上部テーブル）
    # =========================
    add_title("一次対応")

    # 画面合わせ：ユーザー番号=customerID、問合せ者ユーザーID=pass_1
    user_no = (note.customerID or "").strip()
    user_id = (note.pass_1 or "").strip()

    occurred = _compose_dt(
        note.SDATE_Y, note.SDATE_M, note.SDATE_D, note.STIME_H, note.STIME_M
    )
    started = _compose_dt(
        note.TDATE_Y, note.TDATE_M, note.TDATE_D, note.TTIME_H, note.TTIME_M
    )

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("問題番号", _esc(note.mng_no)))
    parts.append(_kv_row("ユーザー番号", _esc(user_no)))
    parts.append(_kv_row("問合せ者ユーザーID", _esc(user_id)))
    parts.append(_kv_row("会社CD", _esc(note.customercompanycd)))
    parts.append(_kv_row("問合せ発生時間", _esc(occurred)))
    parts.append(_kv_row("対応開始時間", _esc(started)))
    parts.append("</table>")

    # 事業所/所属/連絡（PDFの上部ブロックに相当）
    office_name = _pick_first(note.customername, note.SEC3)
    office_kana = _pick_first(note.kana, note.es_namew)
    affiliation = _join_nonempty(note.sec1, note.SEC2, note.SEC3, sep=" / ")
    address = _join_nonempty(note.ADDRESS1, note.ADDRESS2, note.ADDRESS3, sep="\n")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("事業所名", _esc(office_name)))
    parts.append(_kv_row("事業所名（カナ）", _esc(office_kana)))
    parts.append(_kv_row("所属", _esc(affiliation)))
    parts.append(_kv_row("部門名", _esc(note.BUMON)))
    parts.append(_kv_row("住所", _nl2br(address)))
    parts.append(_kv_row("電話", _esc(note.tel)))
    parts.append(_kv_row("FAX", _esc(note.fax)))
    parts.append("</table>")

    # 問合せ者（氏名/カナ/連絡先）
    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("問合せ者氏名", _esc(note.customername_1)))
    parts.append(_kv_row("問合せ者氏名（カナ）", _esc(note.customername_2)))
    # 連絡先はPDF上「携帯/内線」だが、実データ的にはここに入ることが多い想定で並べる
    parts.append(_kv_row("連絡先", _esc(_pick_first(note.mobile_tel_no, note.customerkeitai))))
    parts.append("</table>")

    # =========================
    # 2) 一次 問い合わせ内容（下部3枠）
    # =========================
    add_title("一次 問い合わせ内容")

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    add_text_row("質問概要", note.outline)

    # 問合せ内容（詳細）：body/Detail のリッチテキストを優先。
    detail_main = _pick_first(note.body, note.Detail)
    add_rich_row("問合せ内容（詳細）", detail_main)
    detail_extra = _pick_first(note.body_1, note.Detail_1)
    if detail_extra and detail_extra != detail_main:
        add_rich_row("問合せ内容（詳細・追記）", detail_extra)
    if (note.inquiry or "").strip():
        add_text_row("問合せ内容（補足）", note.inquiry)

    # 対応内容（最終回答）：answer → 無ければ Measure/Memo/TAIOU/Detail_1 の順で補完
    answer_like = _pick_first(note.answer, note.Measure, note.Memo if hasattr(note, "Memo") else None, note.TAIOU, note.Detail_1)
    add_rich_row("対応内容（最終回答）", answer_like)

    parts.append("</table>")

    # =========================
    # 3) 管理情報（PDFの2ページ相当を要約して1ページ内に）
    # =========================
    add_title("管理情報")

    closed = _pick_first(
        note.CloseDateTime,
        _join_nonempty(note.ReplyDate, note.ReplyTime, sep=" "),
    )

    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("対応状況", _esc(_pick_first(note.status, note.Status, note.ActionStatus))))
    parts.append(_kv_row("OPEN中ステータス", _esc(note.status_open)))
    parts.append(_kv_row("完了タイプ", _esc(note.statusTYPE)))
    parts.append(_kv_row("重要度", _esc(note.urgent)))
    parts.append(_kv_row("対応完了日時", _esc(closed)))
    parts.append(_kv_row("対応手段", _esc(note.TAIOU)))
    parts.append(_kv_row("レベル", _esc(note.LEVEL2)))
    parts.append("</table>")

    # カテゴリ（必要最低限でPDF寄せ）
    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("カテゴリ1", _esc(note.category1)))
    parts.append(_kv_row("カテゴリ2", _esc(note.category2)))
    parts.append(_kv_row("カテゴリ3", _esc(note.category3)))
    parts.append(_kv_row("カテゴリ4", _esc(note.category4)))
    parts.append(_kv_row("カテゴリ5", _esc(note.category5)))
    parts.append(_kv_row("カテゴリ6", _esc(note.category6)))
    parts.append("</table>")

    # Office/端末系（あれば）
    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("O365License", _esc(note.O365License)))
    parts.append(_kv_row("OutlookApri", _esc(note.OutlookApri)))
    parts.append(_kv_row("BROWSER", _esc(note.BROWSER)))
    parts.append(_kv_row("PCNAME", _esc(note.PCNAME)))
    parts.append(_kv_row("MailAddress", _esc(note.MailAddress)))
    parts.append("</table>")

    # =========================
    # 4) 履歴（PDFの履歴/添付資料っぽい部分）
    # =========================
    add_title("履歴")

    history = _pick_first(note.lasthistory, note.history)
    if history and "|" in history:
        rows = [x.strip() for x in history.split("|") if x.strip()]
        parts.append("<table style='width:100%; border-collapse:collapse;'>")
        for line in rows:
            # PDFは「日時 担当者 状態 ...」の1行表現なので、ここは行として縦に並べる
            parts.append(_kv_row("履歴", _esc(line)))
        parts.append("</table>")
    else:
        parts.append("<table style='width:100%; border-collapse:collapse;'>")
        add_text_row("履歴", history)
        parts.append("</table>")

    # =========================
    # 5) 添付 / Notesリンク
    # =========================
    add_title("添付・リンク")

    # 添付（表示用）
    if getattr(note, "attachments", None):
        li = "".join(
            f"<li>{_esc(a)}</li>"
            for a in (note.attachments or [])
            if str(a).strip()
        )
        parts.append("<div><b>添付資料</b></div>")
        parts.append("<ul>" + li + "</ul>" if li else "<span style='color:#888;'>（なし）</span>")
    else:
        parts.append("<div><b>添付資料</b></div><span style='color:#888;'>（なし）</span>")

    # Notesリンク（doclink等）
    notes_links_li: list[str] = []
    for s in (getattr(note, "notes_links", None) or []):
        if not str(s).strip():
            continue
        if "|" in s:
            desc, href = [x.strip() for x in s.split("|", 1)]
            notes_links_li.append(f"<li><a href='{_esc(href)}'>{_esc(desc)}</a></li>")
        else:
            notes_links_li.append(f"<li><a href='{_esc(s)}'>{_esc(s)}</a></li>")

    parts.append("<div style='margin-top:6px;'><b>Notesリンク</b></div>")
    parts.append(
        "<ul>" + "".join(notes_links_li) + "</ul>"
        if notes_links_li
        else "<span style='color:#888;'>（なし）</span>"
    )

    # =========================
    # 6) ソース情報（任意）
    # =========================
    if source_file is not None and row_no is not None:
        parts.append(
            "<div style='margin-top:10px; color:#888; font-size:12px;'>"
            f"Source: {_esc(source_file)} / row {row_no}"
            "</div>"
        )

    return container_start + "\n".join(parts) + "</div>"
