# dxl_to_model.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import fields
from typing import Dict, List, Optional

from main.models.SyogaiDb import SyogaiDbRaw

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}


def _join_clean(values: List[str]) -> str:
    """複数値を 1 文字列にまとめる（空は落として、改行で結合）。"""
    vals = [v.strip() for v in values if (v or "").strip()]
    # 空白が多すぎると見づらいので軽く正規化（必要なら外してOK）
    vals = [re.sub(r"[ \t]+", " ", v) for v in vals]
    return "\n".join(vals)


def _extract_item_as_str(item: ET.Element) -> Optional[str]:
    """
    <item> から「人間が読める文字列」を抜く。
    - text / number / datetime を優先
    - richtext は itertext() でテキスト化
    """
    # richtext
    rich = item.find("./dxl:richtext", DXL_NS)
    if rich is not None:
        txt = "".join(rich.itertext()).strip()
        return txt or None

    # text
    texts = [t.text or "" for t in item.findall(".//dxl:text", DXL_NS)]
    if texts:
        s = _join_clean(texts)
        return s or None

    # number
    nums = [n.text or "" for n in item.findall(".//dxl:number", DXL_NS)]
    if nums:
        s = _join_clean(nums)
        return s or None

    # datetime（中身は要素により違うので itertext を全部結合）
    dts = []
    for dt in item.findall(".//dxl:datetime", DXL_NS):
        dts.append("".join(dt.itertext()).strip())
    if dts:
        s = _join_clean(dts)
        return s or None

    # fallback：item全体の文字（タグ除去済みのテキスト）
    fallback = "".join(item.itertext()).strip()
    return fallback or None


def _extract_attachments(root: ET.Element) -> List[str]:
    """
    $FILE から添付ファイル名だけ取り出す（実体はここでは扱わない）
    """
    names: List[str] = []
    for item in root.findall(".//dxl:item[@name='$FILE']", DXL_NS):
        for f in item.findall(".//dxl:file", DXL_NS):
            nm = f.get("name") or ""
            nm = nm.strip()
            if nm:
                names.append(nm)
    return names


def _extract_doclinks(root: ET.Element) -> List[str]:
    """
    doclink を「置換しやすい仮リンク文字列」にする
    例: notesdoc:<ReplicaId>:<UNID> | <description>
    """
    links: List[str] = []
    for dl in root.findall(".//dxl:doclink", DXL_NS):
        doc = (dl.get("document") or "").strip()
        db = (dl.get("database") or "").strip()
        desc = (dl.get("description") or "").strip()

        if doc and db:
            href = f"notesdoc:{db}:{doc}"
        else:
            # 情報不足なら raw で残す
            href = f"notesdoc:unknown:{doc or ''}"

        if desc:
            links.append(f"{desc} | {href}")
        else:
            links.append(href)
    return links


def dxl_to_onenote_row(dxl_path: str) -> SyogaiDbRaw:
    """
    DXLファイル1件 → SyogaiDbRaw（全部str）
    - SyogaiDbRawに存在するフィールド名はそのままセット
    - 存在しないフィールドは extra に入れる
    - 添付名は attachments、doclinkは notes_links に入れる
    """
    root = ET.parse(dxl_path).getroot()

    # SyogaiDbRaw が持つフィールド名セット（extra/attachments/notes_links含む）
    model_field_names = {f.name for f in fields(SyogaiDbRaw)}

    # SyogaiDbRawに渡すkwargs
    kwargs: Dict[str, object] = {}

    extra: Dict[str, str] = {}

    # item を全部走査
    for item in root.findall(".//dxl:item", DXL_NS):
        name = item.get("name")
        if not name:
            continue

        # 添付は別枠で処理するのでここではスキップ
        if name == "$FILE":
            continue

        v = _extract_item_as_str(item)
        if v is None:
            continue

        if name in model_field_names:
            # 既に値が入っている場合（同名itemが複数）→改行追記
            prev = kwargs.get(name)
            if isinstance(prev, str) and prev.strip():
                kwargs[name] = prev + "\n" + v
            else:
                kwargs[name] = v
        else:
            # モデル未定義は extra へ
            if name in extra and extra[name].strip():
                extra[name] = extra[name] + "\n" + v
            else:
                extra[name] = v

    # extra / 添付 / doclink を詰める
    if "extra" in model_field_names:
        kwargs["extra"] = extra

    if "attachments" in model_field_names:
        kwargs["attachments"] = _extract_attachments(root)

    if "notes_links" in model_field_names:
        kwargs["notes_links"] = _extract_doclinks(root)

    # frozen dataclass なのでコンストラクタで一発生成
    return SyogaiDbRaw(**kwargs)  # type: ignore[arg-type]
