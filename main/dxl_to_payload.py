# dxl_to_payload.py
from __future__ import annotations

import base64
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from typing import Optional, List, Tuple, Dict

from .models import OneNoteRow, BinaryPart
from .dxl_to_model import dxl_to_onenote_row  # 既存
from .dxl_attachments import extract_attachments_from_dxl  # 追加

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}

# Graph制約：Presentation + バイナリ最大5（合計6パート）
MAX_BINARY_PARTS_PER_PAGE = 5


# DXL内の画像タグ名 -> MIMEタイプ
_BINARY_TAG_TO_MIME = {
    "gif": "image/gif",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
}


def _local_tag(tag: str) -> str:
    """XMLの名前空間を剥がしてローカル名だけ返す。"""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _safe_px(v: Optional[str]) -> Optional[int]:
    """px表記や数値文字列から幅/高さを安全に抽出する。"""
    if not v:
        return None
    m = re.search(r"(\d+)", v)
    return int(m.group(1)) if m else None


def _par_text_without_binary(par: ET.Element) -> str:
    """
    par 内のテキストを取るが、バイナリ系/添付参照系は本文に混ぜない。
    ※ attachmentref はファイル名などが入っていても、object化するので本文には出さない
    """
    skip = {
        "picture",
        "notesbitmap",
        "gif",
        "png",
        "jpeg",
        "jpg",
        "filedata",
        "attachmentref",
    }

    def walk(el: ET.Element) -> str:
        tag = _local_tag(el.tag)
        if tag in skip:
            return el.tail or ""

        s = el.text or ""
        for ch in list(el):
            s += walk(ch)
        s += el.tail or ""
        return s

    return re.sub(r"\s+\n", "\n", walk(par)).strip()


def _attachment_object_html(*, part_name: str, filename: str, mime: str) -> str:
    """
    OneNote: 添付ファイルは <object> で埋め込む
    data="name:att1" が multipart のキーと対応する
    """
    fn = html.escape(filename, quote=True)
    mt = html.escape(mime or "application/octet-stream", quote=True)
    pn = html.escape(part_name, quote=True)
    return (
        "<div style='margin:8px 0; padding:10px; border:1px solid #e3e3e3; "
        "border-radius:10px; background:#fff;'>"
        f"<object data='name:{pn}' data-attachment='{fn}' type='{mt}'></object>"
        "</div>"
    )


def _picture_to_html_and_parts(
    pic: ET.Element,
    *,
    field_name: str,
    part_prefix: str,
    parts: List[BinaryPart],
) -> Optional[str]:
    """<picture> を見つけたら画像BinaryPartを積み、<img> HTMLを返す（対応できない場合 None）。"""
    w = _safe_px(pic.get("width"))
    h = _safe_px(pic.get("height"))

    for child in list(pic):
        tag = _local_tag(child.tag)
        mime = _BINARY_TAG_TO_MIME.get(tag)
        if not mime:
            continue

        b64 = (child.text or "").strip()
        if not b64:
            continue

        data = base64.b64decode(b64)
        part_name = f"{part_prefix}{len(parts) + 1}"
        filename = f"{part_name}.{tag}"

        parts.append(
            BinaryPart(
                name=part_name,
                filename=filename,
                content_type=mime,
                data=data,
                origin_field=field_name,
            )
        )

        style = "max-width:100%;"
        if w:
            style += f" width:{w}px;"
        if h:
            style += f" height:{h}px;"

        return (
            f"<div style='margin:8px 0;'>"
            f"<img src='name:{html.escape(part_name)}' style='{style}'/>"
            f"</div>"
        )

    return None


def _table_to_html(
    table_el: ET.Element,
    *,
    field_name: str,
    part_prefix: str,
    parts: List[BinaryPart],
    attachment_slots: Dict[str, str],
    attachment_mimes: Dict[str, str],
) -> str:
    """
    richtext 内の <table> をHTML tableに起こす。
    - “基本情報”のkvテーブルと見た目が被らないよう、カード＋別デザインにする
    - セル内の <par> は最低限テキスト化（画像/添付refがあればそれも可能な範囲で出す）
    """
    rows_html: List[str] = []

    tablerows = table_el.findall("dxl:tablerow", DXL_NS)
    for r_i, tr in enumerate(tablerows):
        cells_html: List[str] = []
        cells = tr.findall("dxl:tablecell", DXL_NS)

        for td in cells:
            # セル内に picture があれば画像として出す（あれば）
            pic = td.find(".//dxl:picture", DXL_NS)
            if pic is not None:
                img_html = _picture_to_html_and_parts(
                    pic, field_name=field_name, part_prefix=part_prefix, parts=parts
                )
                if img_html:
                    cell_body = img_html
                else:
                    cell_body = "<span style='color:#888;'>[画像（未対応形式）]</span>"
                cells_html.append(
                    f"<td style='border:1px solid #ddd; padding:6px; vertical-align:top;'>{cell_body}</td>"
                )
                continue

            # 添付参照がセル内にあれば object を出す（可能なら）
            attrefs = td.findall(".//dxl:attachmentref", DXL_NS)
            if attrefs:
                segs: List[str] = []
                for a in attrefs:
                    fn = (a.get("displayname") or a.get("name") or "").strip()
                    if not fn:
                        continue
                    slot = attachment_slots.get(fn)
                    if slot:
                        segs.append(
                            _attachment_object_html(
                                part_name=slot,
                                filename=fn,
                                mime=attachment_mimes.get(fn, "application/octet-stream"),
                            )
                        )
                    else:
                        segs.append(f"<div style='color:#888;'>[添付: {html.escape(fn)}]</div>")
                cell_body = "".join(segs) if segs else ""
                cells_html.append(
                    f"<td style='border:1px solid #ddd; padding:6px; vertical-align:top;'>{cell_body}</td>"
                )
                continue

            # テキスト
            txt = "".join(td.itertext()).strip()
            txt = re.sub(r"\s+\n", "\n", txt)
            safe = html.escape(txt).replace("\n", "<br/>") if txt else ""
            cells_html.append(
                f"<td style='border:1px solid #ddd; padding:6px; vertical-align:top;'>{safe}</td>"
            )

        # 1行目はヘッダーっぽく
        if r_i == 0:
            cells_html = [
                c.replace("padding:6px;", "padding:7px; font-weight:bold; background:#f2f7ff;")
                for c in cells_html
            ]

        rows_html.append("<tr>" + "".join(cells_html) + "</tr>")

    return (
        "<div style='margin:10px 0; padding:10px; border:1px solid #cfd7e6; "
        "border-radius:12px; background:#fbfcff;'>"
        "<div style='font-size:12px; color:#667; margin-bottom:6px;'>表</div>"
        "<table style='border-collapse:collapse; width:100%;'>"
        + "".join(rows_html)
        + "</table>"
        "</div>"
    )


def _richtext_item_to_html_and_parts(
    item_el: ET.Element,
    *,
    field_name: str,
    part_prefix: str,
    attachment_slots: Dict[str, str],
    attachment_mimes: Dict[str, str],
) -> Tuple[str, List[BinaryPart]]:
    """
    <item name="Detail"> の <richtext> を
    - HTML（画像位置・添付位置・表）
    - BinaryPart（画像）
    に変換する。
    """
    rt = item_el.find("dxl:richtext", DXL_NS)
    if rt is None:
        return "", []

    parts: List[BinaryPart] = []
    out: List[str] = []

    # richtext直下の子を“順番通り”に処理（parとtableが混在するため）
    for child in list(rt):
        t = _local_tag(child.tag)

        if t == "par":
            par = child

            # 1) 添付参照（本文中の位置を復元）
            attrefs = par.findall(".//dxl:attachmentref", DXL_NS)
            if attrefs:
                label = _par_text_without_binary(par)
                if label:
                    out.append(f"<p>{html.escape(label)}</p>")

                for a in attrefs:
                    fn = (a.get("displayname") or a.get("name") or "").strip()
                    if not fn:
                        continue

                    slot = attachment_slots.get(fn)
                    if slot:
                        out.append(
                            _attachment_object_html(
                                part_name=slot,
                                filename=fn,
                                mime=attachment_mimes.get(fn, "application/octet-stream"),
                            )
                        )
                    else:
                        # 送れなかった（Graph制約など）
                        out.append(
                            f"<div style='color:#888; margin:6px 0;'>"
                            f"[添付: {html.escape(fn)}（未送信）]"
                            f"</div>"
                        )
                continue

            # 2) 画像
            pic = par.find(".//dxl:picture", DXL_NS)
            if pic is not None:
                img_html = _picture_to_html_and_parts(
                    pic, field_name=field_name, part_prefix=part_prefix, parts=parts
                )
                if img_html:
                    out.append(img_html)
                # 未対応なら何も出さない（アイコン等は不要方針）
                continue

            # 3) テキスト
            txt = _par_text_without_binary(par)
            if txt:
                out.append(f"<p>{html.escape(txt)}</p>")
            else:
                out.append("<p><br/></p>")
            continue

        if t == "table":
            out.append(
                _table_to_html(
                    child,
                    field_name=field_name,
                    part_prefix=part_prefix,
                    parts=parts,
                    attachment_slots=attachment_slots,
                    attachment_mimes=attachment_mimes,
                )
            )
            continue

        # その他は現状無視（pardef等）
        continue

    return "\n".join(out), parts


def _attachments_to_parts(attachment_objs, *, name_map: Dict[str, str]) -> List[BinaryPart]:
    """$FILEから抽出した添付を、Graph multipart用 BinaryPart に変換（nameは本文側の割当を使う）。"""
    parts: List[BinaryPart] = []
    for a in attachment_objs:
        part_name = name_map.get(a.filename)
        if not part_name:
            continue
        parts.append(
            BinaryPart(
                name=part_name,
                filename=a.filename,
                content_type=a.mime,
                data=a.content,
                origin_field="$FILE",
            )
        )
    return parts


def dxl_to_onenote_payload(dxl_path: str, *, rich_fields: List[str]) -> Tuple[OneNoteRow, List[BinaryPart]]:
    """
    DXL -> (OneNoteRow, parts)
    - OneNoteRow: 文字フィールドは既存ロジック、rich_fieldsはDXL直読みでHTMLへ差し替え
    - parts: rich_fields内の画像 + $FILE（添付）のうち送れる分を返す
    """
    note = dxl_to_onenote_row(dxl_path)
    root = ET.parse(dxl_path).getroot()

    replace_kwargs = {}

    # --- $FILE 添付（全件）を先に抽出してマップ化
    attachment_objs_all = extract_attachments_from_dxl(dxl_path) or []
    attachment_by_name = {a.filename: a for a in attachment_objs_all}

    # ついでにmime参照用
    attachment_mimes_all = {a.filename: (a.mime or "application/octet-stream") for a in attachment_objs_all}

    # --- 本文中に登場する添付ref名を “登場順” に拾う（rich_fieldsの順に走査）
    attref_names_in_body: List[str] = []
    for field_name in rich_fields:
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue
        rt = item.find("dxl:richtext", DXL_NS)
        if rt is None:
            continue

        for el in rt.iter():
            if _local_tag(el.tag) == "attachmentref":
                fn = (el.get("displayname") or el.get("name") or "").strip()
                if fn:
                    attref_names_in_body.append(fn)

    # 重複を潰しつつ順序は保持
    seen = set()
    attref_names_in_body = [x for x in attref_names_in_body if not (x in seen or seen.add(x))]

    parts_all: List[BinaryPart] = []

    # --- いったん画像HTML生成に必要な “添付スロット割当” を準備（この時点では枠未確定）
    # ここでは「送れた添付だけ slot を持つ」ので、まずは空で作っておく → 画像数が決まってから割り当てる
    attachment_slots: Dict[str, str] = {}

    # --- 画像（rich_fields）を先に生成（既存方針：画像優先）
    for field_name in rich_fields:
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue

        field_html, img_parts = _richtext_item_to_html_and_parts(
            item,
            field_name=field_name,
            part_prefix=f"{field_name.lower()}_img_",
            attachment_slots=attachment_slots,          # まだ空（添付objectは後でslotが入ると有効化）
            attachment_mimes=attachment_mimes_all,
        )
        if field_html:
            replace_kwargs[field_name] = field_html
        parts_all.extend(img_parts)

    # --- 添付は「画像で使った残り枠」だけ送る（Graph制約）
    remain = max(0, MAX_BINARY_PARTS_PER_PAGE - len(parts_all))

    # 送る候補：本文中で参照された順 → 余ればその他
    send_names: List[str] = []
    for fn in attref_names_in_body:
        if fn in attachment_by_name:
            send_names.append(fn)
    if len(send_names) < remain:
        for fn in attachment_by_name.keys():
            if fn not in send_names:
                send_names.append(fn)

    send_names = send_names[:remain]
    attachment_objs_send = [attachment_by_name[n] for n in send_names]

    # slot割当（本文中の <object data="name:attX"> に使う）
    attachment_slots = {fn: f"att{i}" for i, fn in enumerate(send_names, start=1)}

    # note側には “全ファイル名” は残す
    if attachment_objs_all:
        replace_kwargs["attachments"] = [a.filename for a in attachment_objs_all]
        replace_kwargs["attachment_objs"] = attachment_objs_send  # 使ってるなら維持

    # --- ここで「添付slotが確定」したので、rich_fields のHTMLを作り直して“本文中にobjectを差し込む”
    # （最初の生成はslot空なので、attachmentrefがあってもobject化されない）
    for field_name in rich_fields:
        item = root.find(f".//dxl:item[@name='{field_name}']", DXL_NS)
        if item is None:
            continue
        field_html, img_parts_dummy = _richtext_item_to_html_and_parts(
            item,
            field_name=field_name,
            part_prefix=f"{field_name.lower()}_img_",
            attachment_slots=attachment_slots,
            attachment_mimes=attachment_mimes_all,
        )
        if field_html:
            replace_kwargs[field_name] = field_html

    # 添付BinaryPartsを追加
    parts_all.extend(_attachments_to_parts(attachment_objs_send, name_map=attachment_slots))

    # frozen dataclass なので replace で差し替え
    if replace_kwargs:
        note = replace(note, **replace_kwargs)

    # 最終保険：Graph制約に合わせて5件まで（Presentation除く）
    parts_all = parts_all[:MAX_BINARY_PARTS_PER_PAGE]

    return note, parts_all
