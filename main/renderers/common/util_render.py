# util_render.py
from __future__ import annotations
import re
from typing import Optional

def _normalize_notes_dt(s: Optional[str]) -> str:
    """Notesの日時表記を人間が読みやすい形に整形。"""
    if not s:
        return ""
    t = str(s).strip()

    # Some DXL exports append a base64-like suffix after the date/time value.
    m = re.fullmatch(r"(\d{8})([A-Za-z0-9+/=]+)", t)
    if m:
        t = m.group(1)
    else:
        m = re.fullmatch(
            r"(\d{8}T\d{6}(?:,\d+)?(?:[+-]\d{2})?)([A-Za-z0-9+/=]+)",
            t,
        )
        if m:
            t = m.group(1)
        else:
            m = re.fullmatch(r"(\d{4}/\d{2}/\d{2})([A-Za-z0-9+/=]+)", t)
            if m:
                t = m.group(1)
            else:
                m = re.fullmatch(
                    r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})([A-Za-z0-9+/=]+)",
                    t,
                )
                if m:
                    t = m.group(1)

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
