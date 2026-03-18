# fill_template.py
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, Optional, Set


DXL_NS = {"dxl": "http://www.lotus.com/dxl"}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def _escape_value(v: str) -> str:
    s = v.strip()
    s = html.escape(s, quote=False)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "<br/>")
    return s


def _escape_value_or_nbsp(v: str) -> str:
    if v.strip() == "":
        return "&nbsp;"
    return _escape_value(v)


def _rewrite_richtext_field_wrappers(template_html: str, raw_fields: Set[str]) -> str:
    """
    richtext(raw_fields) placeholder that is wrapped by span/span is invalid when
    injected HTML contains block tags (<p>, <div>, <table> ...). Convert only
    those wrappers to div/div to keep HTML valid.
    """
    out = template_html
    for key in raw_fields:
        pat = re.compile(
            rf"(?is)"
            rf"<span(?P<w_attr>[^>]*\bclass\s*=\s*['\"][^'\"]*\bnotes-field-wrap\b[^'\"]*['\"][^>]*)>"
            rf"\s*<span(?P<f_attr>[^>]*\bclass\s*=\s*['\"][^'\"]*\bnotes-field\b[^'\"]*['\"][^>]*)>"
            rf"\s*\{{\{{\s*{re.escape(key)}\s*\}}\}}\s*"
            rf"</span>\s*</span>"
        )
        out = pat.sub(
            lambda m: (
                f"<div{m.group('w_attr')}>"
                f"<div{m.group('f_attr')}>{{{{{key}}}}}</div>"
                f"</div>"
            ),
            out,
        )
    return out


def fill_template(
    *,
    template_html: str,
    values: Dict[str, str],
    raw_fields: Optional[Set[str]] = None,
) -> str:
    raw_fields = raw_fields or set()
    template_html = _rewrite_richtext_field_wrappers(template_html, raw_fields)

    def repl(m: re.Match) -> str:
        key = m.group(1)
        raw = values.get(key, "")
        v = str(raw).strip() if raw is not None else ""
        if key in raw_fields:
            return v
        return _escape_value_or_nbsp(v)

    return _PLACEHOLDER_RE.sub(repl, template_html)

def resolve_template_html_path(template_html_path: str | Path) -> Path:
    template_path = Path(template_html_path)
    if template_path.is_dir():
        candidates = sorted(template_path.glob("*.html"))
        if not candidates:
            raise FileNotFoundError(f"Template HTML not found in dir: {template_path}")
        if len(candidates) > 1:
            names = ", ".join(p.name for p in candidates)
            raise ValueError(
                f"Multiple template HTML files in dir: {template_path}. "
                f"Candidates: {names}"
            )
        return candidates[0]
    return template_path