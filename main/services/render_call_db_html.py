# render_call_db_html.py
from __future__ import annotations

from main.models.CallDb import CallDbRaw
from main.services.util_render import (
    _esc,
    _join_nonempty,
    _kv_row,
    _nl2br,
    add_text_row,
    add_title,
    compose_dt,
    pick_first,
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

    def add_section_title(title: str) -> None:
        add_title(parts, title)

    def add_section_text_row(label: str, s: str | None) -> None:
        add_text_row(parts, label, s)

    # =========================
    # 0) ヘッダー（1ページ内の見出し）
    # =========================
    # OneNoteページタイトル自体は title_fields で別途付く想定だが、
    # HTML内にも読みやすい見出しとして出す。
    # headline = _join_nonempty(note.mng_no, note.outline, sep="  /  ")
    # parts.append(
    #     "<div style='font-size:18px; font-weight:bold; margin:4px 0 10px;'>"
    #     f"{_esc(headline) if headline else 'CallDB'}"
    #     "</div>"
    # )

    # =========================
    # 1) 一次対応（上部テーブル）
    # =========================
    add_section_title("一次対応")



    occurred = compose_dt(
        note.SDATE_Y, note.SDATE_M, note.SDATE_D, note.STIME_H, note.STIME_M
    )
    started = compose_dt(
        note.TDATE_Y, note.TDATE_M, note.TDATE_D, note.TTIME_H, note.TTIME_M
    )


    parts.append("<table style='width:100%; border-collapse:collapse;'>")
    parts.append(_kv_row("問題番号", _esc(note.mng_no)))
    parts.append(_kv_row("ユーザー番号", _esc(note.customerno)))
    parts.append(_kv_row("会社CD", _esc(note.customercompanycd)))
    parts.append("</table>")



    # 事業所/所属/連絡
    office_name = pick_first(note.customername, note.SEC3)
    office_kana = pick_first(note.kana, note.es_namew)
    affiliation = _join_nonempty(note.sec1, note.SEC2, note.SEC3, sep=" / ")
    address = _join_nonempty(note.ADDRESS1, note.ADDRESS2, note.ADDRESS3, sep=" ")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("問合せ発生時間", _esc(occurred)))
    parts.append(_kv_row("対応開始時間", _esc(started)))

    parts.append("<br>")

    parts.append(_kv_row("事業所名", _esc(office_name)))
    parts.append(_kv_row("事業所名（カナ）", _esc(office_kana)))
    parts.append(_kv_row("所属", _esc(affiliation)))
    parts.append(_kv_row("住所", _nl2br(address)))
    parts.append(_kv_row("電話", _esc(note.tel)))
    parts.append(_kv_row("FAX", _esc(note.fax)))
    parts.append(_kv_row("部門名", _esc(note.BUMON)))
    parts.append(_kv_row("会社区分", _esc(note.KAISHA)))
    parts.append("</table>")

    parts.append("<br>")

    # 問合せ者（氏名/カナ/連絡先）
    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("問合せ者氏名", _esc(note.customername_1)))
    parts.append(_kv_row("問合せ者氏名（カナ）", _esc(note.customername_2)))
    parts.append(_kv_row("問合せ者ユーザーID", _esc(note.customerID)))
    parts.append(_kv_row("連絡先", _esc(pick_first(note.mobile_tel_no, note.customerkeitai))))
    parts.append("</table>")



    # =========================
    # 一次 問い合わせ内容
    # =========================

    parts.append("<br>")
    add_section_title("一次 問い合わせ内容")

    endDateTime = compose_dt(note.EDATE_Y, note.EDATE_M, note.EDATE_D, note.ETIME_H, note.ETIME_M)

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("質問概要", _esc(note.outline)))
    # parts.append(_kv_row("問合せ内容（詳細）", note.inquiry))
    # add_rich_row("対応内容（最終回答）", note.answer)
    add_section_text_row("問合せ内容（詳細）", note.inquiry)
    add_section_text_row("対応内容（最終回答）", note.answer)

    parts.append(_kv_row("対応完了日時", endDateTime))

    parts.append("</table>")




    # =========================
    # 対象者情報
    # =========================

    parts.append("<br>")
    add_section_title("対象者情報")
    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("対象者氏名", _esc(note.name)))
    parts.append(_kv_row("ADユーザーID", _esc(note.ADID)))
    parts.append(_kv_row("コンピューター名", _esc(note.pc_name)))
    parts.append(_kv_row("メールアドレス", _esc(note.MailAddress)))
    parts.append("</table>")

    # =========================
    # Office365情報
    # =========================

    parts.append("<br>")
    add_section_title("Office365情報")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("O365ライセンス", _esc(note.O365License)))
    parts.append(_kv_row("Outlook使用アプリ", _esc(note.OutlookApri)))
    parts.append(_kv_row("利用環境_端末", _esc(note.plathome)))
    parts.append(_kv_row("スマートデバイス回線番号", _esc(note.mobile_tel_no)))

    O365SYURUI_BROWSER = _join_nonempty(note.O365SYURUI, note.BROWSER, " ")
    parts.append(_kv_row("利用環境_種類", _esc(O365SYURUI_BROWSER)))
    parts.append(_kv_row("実施作業", _esc(note.SAGYO)))
    parts.append("</table>")


    # =========================
    # 
    # =========================

    parts.append("<br>")
    add_section_title("")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("問合せ種別", _esc(note.category1)))
    parts.append(_kv_row("問合せチャネル", _esc(note.category5)))
    parts.append(_kv_row("問合せ内容", _esc(note.category3)))
    parts.append(_kv_row("問合せ内容（詳細）", _esc(note.category4)))
    # parts.append(_kv_row("カテゴリ5", _esc(note.category5)))
    parts.append(_kv_row("カテゴリ6", _esc(note.category6)))
    parts.append("</table>")

    add_section_title("サポートデスクDB")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("カテゴリ1", _esc(note.S_Category1)))
    parts.append(_kv_row("カテゴリ2", _esc(note.S_Category2)))
    parts.append(_kv_row("カテゴリ3", _esc(note.S_Category3)))
    parts.append(_kv_row("件名", _esc(note.S_Outline)))
    parts.append("</table>")

    add_section_title("ヘルプマニュアル")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("カテゴリ1", _esc(note.H_Category1)))
    parts.append(_kv_row("カテゴリ2", _esc(note.H_Category2)))
    parts.append(_kv_row("件名", _esc(note.H_Outline)))
    parts.append("</table>")

    add_section_title("関連部門のエスカレーション先")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("システム名", _esc(note.Escalation_1)))
    parts.append(_kv_row("送信先の宛先", _esc(note.SSendTo_1)))
    parts.append(_kv_row("送信先のCC", _esc(note.SCC_1)))
    parts.append("</table>")

    add_section_title("対応依頼先")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("システム名", _esc(note.Escalation_0_1)))
    parts.append(_kv_row("送信先の宛先", _esc(note.HSendTo_1)))
    parts.append(_kv_row("送信先のCC", _esc(note.HCC_1)))
    parts.append("</table>")


    parts.append("<br>")

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("Hardware", _esc(note.HW)))
    # parts.append(_kv_row("", _esc(note.)))
    parts.append("</table>")


    parts.append("<br>")
    add_section_title("")
    add_section_title("")
    add_section_title("略！！！")
    add_section_title("")
    add_section_title("")



    parts.append("<br>")
    add_section_title("関連部門")


    SDATE = compose_dt(note.SDATE_Y_2, note.SDATE_M_2, note.SDATE_D_2, note.STIME_H_2, note.STIME_M_2)
    # KDATE = _compose_dt(note.KDATE_Y_2, note.KDATE_M_2, note.KDATE_D_2, note.KTIME_H_2, note.KTIME_M_2)
    CDATE = compose_dt(note.CDATE_Y_2, note.CDATE_M_2, note.CDATE_D_2, note.CTIME_H_2, note.CTIME_M_2)
    EDATE = compose_dt(note.EDATE_Y_2, note.EDATE_M_2, note.EDATE_D_2, note.ETIME_H_2, note.ETIME_M_2)
    ADATE = compose_dt(note.ADATE_Y_2, note.ADATE_M_2, note.ADATE_D_2, note.ATIME_H_2, note.ATIME_M_2)

    parts.append("<table style='width:100%; border-collapse:collapse; margin-top:6px;'>")
    parts.append(_kv_row("区分", _esc(note.Third_Type)))
    parts.append(_kv_row("担当者", _esc(note.Third_Person)))
    parts.append(_kv_row("所属部署", _esc(note.Third_Dept)))
    parts.append(_kv_row("連絡先", _esc(note.Third_Contact)))
    parts.append(_kv_row("受付日時", _esc(SDATE)))
    parts.append(_kv_row("中間回答日時", _esc(CDATE)))
    parts.append(_kv_row("途中経過内容（作業内容）", _esc(note.Third_half)))
    parts.append(_kv_row("最終回答日時", _esc(EDATE)))
    parts.append(_kv_row("回答内容", _esc(note.Third_answer)))
    parts.append(_kv_row("問合せ種別", _esc(note.Second_category1)))

    parts.append(_kv_row("問合せ内容", _esc(note.Second_category2)))
    parts.append(_kv_row("問合せ内容", _esc(note.Second_category3)))

    parts.append(_kv_row("対応時間", _esc(note.JIKAN_2_1)))
    parts.append(_kv_row("調査時間", _esc(note.JIKAN_2_2)))
    parts.append(_kv_row("障害", _esc(note.Trouble_2)))
    parts.append(_kv_row("上長コメント", _esc(note.Third_comment)))
    parts.append(_kv_row("上長承認", _esc(note.Trouble_Approve_2)))
    parts.append(_kv_row("承認日時", _esc(ADATE)))
    parts.append("</table>")



    # parts.append(_kv_row("", _esc(note.)))
    # parts.append(_kv_row("", _esc(note.)))
    # parts.append(_kv_row("", _esc(note.)))
    # parts.append(_kv_row("", _esc(note.)))
    # parts.append(_kv_row("", _esc(note.)))
    # parts.append(_kv_row("", _esc(note.)))
    # parts.append(_kv_row("", _esc(note.)))






    # =========================
    # 添付資料
    # =========================
    parts.append("<br>")
    add_section_title("対応メモ")
    parts.append(note.body_1)



    # =========================
    # 添付資料
    # =========================
    parts.append("<br>")
    add_section_title("添付資料")
    parts.append(note.body)    


    # =========================
    # 履歴
    # =========================
    parts.append("<br>")
    add_section_title("履歴情報")

    history = pick_first(note.lasthistory, note.history)
    if history and "|" in history:
        rows = [x.strip() for x in history.split("|") if x.strip()]
        parts.append("<table style='width:100%; border-collapse:collapse;'>")
        for line in rows:
            # PDFは「日時 担当者 状態 ...」の1行表現なので、ここは行として縦に並べる
            parts.append(_kv_row("履歴", _esc(line)))
        parts.append("</table>")
    else:
        parts.append("<table style='width:100%; border-collapse:collapse;'>")
        add_section_text_row("履歴", history)
        parts.append("</table>")


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
