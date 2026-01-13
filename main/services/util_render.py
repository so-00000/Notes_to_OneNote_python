# util_render.py
from __future__ import annotations

import html
import re
from typing import Optional



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

