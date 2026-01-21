from __future__ import annotations

import html
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set
import re

DXL_NS = {"dxl": "http://www.lotus.com/dxl"}
NON_RENDER_TAGS = {
    "code",
    "formula",
    "lotusscript",
    "numberformat",
    "datetimeformat",
    "keywords",
    "tablecolumn",
}


_TAG_RE = re.compile(r"<[^>]+>")

def _is_blank_html(fragment: str) -> bool:
    """
    HTML断片が「実質空」か判定する。
    - タグ除去
    - &nbsp; や空白だけなら空扱い
    """
    if not fragment:
        return True

    s = fragment
    # よくある空表現を潰す
    s = s.replace("&nbsp;", " ")
    s = s.replace("&#160;", " ")
    s = s.replace("<br/>", " ")
    s = s.replace("<br>", " ")

    # タグ除去
    s = _TAG_RE.sub("", s)
    # エスケープ解除（&amp;等）して判定精度を上げる
    s = html.unescape(s)

    return s.strip() == ""



def _ln(tag: str) -> str:
    """Return localname from '{ns}tag' or 'tag'."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _build_parent_map(root: ET.Element) -> Dict[ET.Element, ET.Element]:
    parent: Dict[ET.Element, ET.Element] = {}
    for p in root.iter():
        for c in list(p):
            parent[c] = p
    return parent


def _collect_hidewhen_text(el: ET.Element) -> Optional[str]:
    """Pick up Hide-When code text under the element, if any."""
    for code in el.findall(".//dxl:code", DXL_NS):
        if code.attrib.get("event", "").lower() == "hidewhen":
            txt = "".join(code.itertext()).strip()
            if txt:
                return txt
    return None


def _collect_hide_attr_chain(el: ET.Element, parent: Dict[ET.Element, ET.Element]) -> Set[str]:
    """Collect 'hide' attribute tokens from this node up to root."""
    modes: Set[str] = set()
    cur = el
    while True:
        hide = cur.attrib.get("hide")
        if hide:
            for tok in hide.split():
                tok = tok.strip()
                if tok:
                    modes.add(tok)
        if cur not in parent:
            break
        cur = parent[cur]
    return modes


def _parse_hide_tokens(hide: str) -> Set[str]:
    return {t.strip() for t in hide.split() if t.strip()}


def _find_body_richtext(root: ET.Element) -> Optional[ET.Element]:
    body = root.find("dxl:body", DXL_NS)
    if body is None:
        return None
    return body.find("dxl:richtext", DXL_NS)


def _guess_design_name(root: ET.Element) -> str:
    name = root.attrib.get("name") or ""
    alias = root.attrib.get("alias") or ""
    if name and alias and name != alias:
        return f"{name} ({alias})"
    return name or alias or "(unknown)"


def _find_subform_dxl(subform_name: str, search_dir: Path) -> Optional[Path]:
    patterns = [
        f"*__SUBFORM__{subform_name}__*.dxl",
        f"*__SUBFORM__{subform_name}*.dxl",
        f"*__SUBFORM__*{subform_name}*__*.dxl",
    ]
    for pat in patterns:
        hits = sorted(search_dir.glob(pat))
        if hits:
            return hits[0]
    return None


def _collect_visible_text(el: ET.Element) -> str:
    parts: List[str] = []

    def walk(node: ET.Element) -> None:
        tag = _ln(node.tag)
        if tag in NON_RENDER_TAGS:
            return
        if node.text:
            parts.append(node.text)
        for child in list(node):
            walk(child)
            if child.tail:
                parts.append(child.tail)

    walk(el)
    return "".join(parts)


@dataclass(frozen=True)
class FieldDef:
    """画面に表示されたフィールド（HTMLに出力されたものだけ）"""
    name: str
    type: Optional[str] = None
    kind: Optional[str] = None
    allow_multivalues: Optional[str] = None  # DXLが文字列なのでそのまま保持
    shared: bool = False


class FormToHtml:
    """Best-effort DXL richtext -> simple HTML (and visible field list)."""

    def __init__(
        self,
        *,
        root: ET.Element,
        search_dir: Path,
        visited_subforms: Optional[Set[str]] = None,
    ):
        self.root = root
        self.parent = _build_parent_map(root)
        self.search_dir = search_dir
        self.visited_subforms = visited_subforms or set()
        self.missing_subforms: Set[str] = set()

        # pardef(id) -> hide tokens（par def=... の参照用）
        self.pardef_hide: Dict[str, Set[str]] = {}
        rich = _find_body_richtext(self.root)
        if rich is not None:
            for pd in rich.findall(".//dxl:pardef", DXL_NS):
                pid = pd.attrib.get("id")
                hide = pd.attrib.get("hide", "")
                if pid and hide:
                    self.pardef_hide[pid] = _parse_hide_tokens(hide)

        # ★「画面に表示された項目」だけを収集する
        self.visible_fields: Dict[str, FieldDef] = {}

    def _should_skip_by_hide(self, el: ET.Element) -> bool:
        """
        方針：hideが絡む要素はすべてHTML変換対象外（=非表示扱い）
        - 自分〜祖先のhide
        - parの場合は pardef参照(def="X") のhide も含める
        """
        modes = _collect_hide_attr_chain(el, self.parent)

        hide = el.attrib.get("hide", "")
        if hide:
            modes |= _parse_hide_tokens(hide)

        if _ln(el.tag) == "par":
            pd_id = el.attrib.get("def")
            if pd_id and pd_id in self.pardef_hide:
                modes |= self.pardef_hide[pd_id]

        return bool(modes)

    def _register_field(self, *, name: str, ftype: str, kind: str, amv: str, shared: bool) -> None:
        """同名は1回だけ登録（最初に見えた属性を採用）"""
        if not name:
            return
        if name in self.visible_fields:
            return
        self.visible_fields[name] = FieldDef(
            name=name,
            type=ftype or None,
            kind=kind or None,
            allow_multivalues=amv or None,
            shared=shared,
        )

    def render_body(self) -> str:
        rich = _find_body_richtext(self.root)
        if rich is None:
            return "<!-- body/richtext not found -->"

        design_name = _guess_design_name(self.root)
        parts: List[str] = []

        parts.append(
            "<style>"
            ".notes-form{font-family:MS PGothic,Meiryo,'Segoe UI',Arial,sans-serif;font-size:11pt;line-height:1.45;color:#222;}"
            ".notes-form table{border-collapse:collapse;width:100%;}"
            ".notes-form td,.notes-form th{border:1px solid #808080;padding:3px 6px;vertical-align:top;}"
            ".notes-form th{background:#efefef;font-weight:normal;}"
            ".notes-form .notes-par{margin:2px 0;}"
            ".notes-form .notes-field{display:inline-block;min-width:6em;min-height:1.2em;border:1px solid #666;background:#fff;padding:1px 4px;border-radius:2px;}"
            ".notes-form .notes-field[data-kind='computed'],"
            ".notes-form .notes-field[data-kind='computedfordisplay'],"
            ".notes-form .notes-field[data-kind='computedwhencomposed']{background:#f7f7f7;color:#555;}"
            ".notes-form .notes-link{color:#0645ad;text-decoration:underline;}"
            ".notes-form .notes-subform{border:1px dashed #aaa;padding:6px;margin:6px 0;background:#fafafa;}"
            ".notes-form .notes-subform-title{font-weight:bold;margin-bottom:4px;}"
            ".notes-form .notes-section{border:1px solid #a0a0a0;margin:6px 0;}"
            ".notes-form .notes-section-title{background:#d9d9d9;padding:2px 6px;font-weight:bold;}"
            ".notes-form .notes-section-body{padding:4px 6px;}"
            ".notes-form .notes-textlist{display:block;margin-left:1em;}"
            "</style>"
        )

        parts.append(
            f"<div class='notes-form' data-design='{html.escape(design_name, quote=True)}'>"
        )
        parts.append(self._render_children(rich))
        parts.append("</div>")

        return "".join(parts)

    def _render_children(self, el: ET.Element) -> str:
        out: List[str] = []
        if el.text:
            out.append(html.escape(el.text))

        for ch in list(el):
            out.append(self._render_node(ch))
            if ch.tail:
                out.append(html.escape(ch.tail))
        return "".join(out)

    def _data_attrs_common(self, el: ET.Element) -> str:
        hide_modes = _collect_hide_attr_chain(el, self.parent)
        hidewhen = _collect_hidewhen_text(el)
        attrs: List[str] = []
        if hide_modes:
            attrs.append(
                f"data-hide-modes='{html.escape(' '.join(sorted(hide_modes)), quote=True)}'"
            )
        if hidewhen:
            hw = hidewhen
            if len(hw) > 2000:
                hw = hw[:2000] + " ..."
            attrs.append(f"data-hidewhen='{html.escape(hw, quote=True)}'")
        return (" " + " ".join(attrs)) if attrs else ""

    def _render_node(self, el: ET.Element) -> str:
        tag = _ln(el.tag)

        # ★ 非表示(hide絡み)は全部変換対象外
        if self._should_skip_by_hide(el):
            return ""

        # Ignore binary/layout heavy blocks we don't map
        if tag in {"compositedata", "embeddedobject", "picture", "button"}:
            return ""

        # Ignore non-visible definitions or code blocks
        if tag in NON_RENDER_TAGS:
            return ""

        # Paragraph definition - skip
        if tag == "pardef":
            return ""

        # Paragraph
        if tag == "par":
            attrs = self._data_attrs_common(el)
            inner = self._render_children(el)
            if not inner.strip():
                return ""  # 空parは出さない
            return f"<div class='notes-par'{attrs}>{inner}</div>"

        # Runs/fonts mostly styling - flatten
        if tag in {"run", "font"}:
            return self._render_children(el)

        # Line breaks/tabs
        if tag in {"break", "linebreak"}:
            return "<br/>"
        if tag == "tab":
            return "&emsp;"

        # Tables
        if tag == "table":
            attrs = self._data_attrs_common(el)
            inner = self._render_children(el)
            if _is_blank_html(inner):
                return ""   # ★空テーブルは消す
            return f"<table{attrs}>{inner}</table>"

        
        if tag == "tablerow":
            attrs = self._data_attrs_common(el)

            cell_htmls: List[str] = []
            any_nonblank = False

            for ch in list(el):
                rendered = self._render_node(ch)
                if rendered:
                    cell_htmls.append(rendered)
                    if not _is_blank_html(rendered):
                        any_nonblank = True

                # tail は tablerow 配下だと基本いらないので無視（必要なら残してもOK）

            # ★ 全セル空なら、この行(tr)ごと出さない
            if not any_nonblank:
                return ""

            return f"<tr{attrs}>{''.join(cell_htmls)}</tr>"


        if tag == "tablecell":
            attrs = self._data_attrs_common(el)
            colspan = el.attrib.get("columnspan") or el.attrib.get("colspan")
            rowspan = el.attrib.get("rowspan")
            extra = ""
            if colspan and colspan.isdigit() and int(colspan) > 1:
                extra += f" colspan='{colspan}'"
            if rowspan and rowspan.isdigit() and int(rowspan) > 1:
                extra += f" rowspan='{rowspan}'"
            inner = self._render_children(el)
            if not inner.strip():
                inner = "&nbsp;"
            return f"<td{extra}{attrs}>{inner}</td>"
        if tag == "tablecellheader":
            attrs = self._data_attrs_common(el)
            inner = self._render_children(el)
            if not inner.strip():
                inner = "&nbsp;"
            return f"<th{attrs}>{inner}</th>"

        if tag == "section":
            attrs = self._data_attrs_common(el)
            inner = self._render_children(el)
            return (
                f"<div class='notes-section'{attrs}>"
                f"<div class='notes-section-body'>{inner}</div>"
                f"</div>"
            )
        if tag == "sectiontitle":
            attrs = self._data_attrs_common(el)
            title = _collect_visible_text(el).strip()
            title = html.escape(title) if title else "&nbsp;"
            return f"<div class='notes-section-title'{attrs}>{title}</div>"

        if tag == "urllink":
            attrs = self._data_attrs_common(el)
            href = el.attrib.get("href", "")
            label = _collect_visible_text(el).strip() or href or "link"
            safe_href = html.escape(href, quote=True)
            return (
                f"<a class='notes-link' href='{safe_href}'{attrs}>"
                f"{html.escape(label)}</a>"
            )

        if tag == "textlist":
            content = _collect_visible_text(el).strip()
            return f"<span class='notes-textlist'>{html.escape(content)}</span>"

        # Field placeholder（ここで「表示された項目」を収集）
        if tag == "field":
            name = el.attrib.get("name", "")
            ftype = el.attrib.get("type", "")
            kind = el.attrib.get("kind", "")
            amv = el.attrib.get("allowmultivalues", "")

            self._register_field(name=name, ftype=ftype, kind=kind, amv=amv, shared=False)

            attrs = [
                "class='notes-field'",
                f"data-field='{html.escape(name, quote=True)}'",
            ]
            if ftype:
                attrs.append(f"data-type='{html.escape(ftype, quote=True)}'")
            if kind:
                attrs.append(f"data-kind='{html.escape(kind, quote=True)}'")
            if amv:
                attrs.append(f"data-allowmultivalues='{html.escape(amv, quote=True)}'")

            common = self._data_attrs_common(el)
            label = html.escape(name)
            return f"<span {' '.join(attrs)}{common}>{{{{{label}}}}}</span>"

        if tag == "sharedfieldref":
            name = el.attrib.get("name", "")
            self._register_field(name=name, ftype="", kind="", amv="", shared=True)

            attrs = [
                "class='notes-field'",
                f"data-field='{html.escape(name, quote=True)}'",
                "data-shared='true'",
            ]
            common = self._data_attrs_common(el)
            label = html.escape(name)
            return f"<span {' '.join(attrs)}{common}>{{{{{label}}}}}</span>"

        # Subform reference: try to expand
        if tag == "subformref":
            name = el.attrib.get("name") or el.attrib.get("subformname") or ""
            attrs = self._data_attrs_common(el)
            safe = html.escape(name)

            if not name:
                return f"<div class='notes-subform'{attrs}>[SUBFORM: (no name)]</div>"

            if name in self.visited_subforms:
                return (
                    f"<div class='notes-subform'{attrs}>"
                    f"<div class='notes-subform-title'>SUBFORM: {safe} (cycle)</div>"
                    f"</div>"
                )

            dxl_path = _find_subform_dxl(name, self.search_dir)
            if dxl_path is None:
                self.missing_subforms.add(name)
                return (
                    f"<div class='notes-subform'{attrs}>"
                    f"<div class='notes-subform-title'>SUBFORM: {safe} (missing DXL)</div>"
                    f"</div>"
                )

            sub_root = ET.parse(dxl_path).getroot()
            sub_rich = _find_body_richtext(sub_root)
            if sub_rich is None:
                self.missing_subforms.add(name)
                return (
                    f"<div class='notes-subform'{attrs}>"
                    f"<div class='notes-subform-title'>SUBFORM: {safe} (no body/richtext)</div>"
                    f"</div>"
                )

            nested_visited = set(self.visited_subforms)
            nested_visited.add(name)
            nested = FormToHtml(
                root=sub_root,
                search_dir=self.search_dir,
                visited_subforms=nested_visited,
            )
            html_inner = nested._render_children(sub_rich)

            # ★ subformで見えたフィールドも親へマージ（=画面表示項目として扱う）
            for k, v in nested.visible_fields.items():
                if k not in self.visible_fields:
                    self.visible_fields[k] = v

            self.missing_subforms.update(nested.missing_subforms)

            return (
                f"<div class='notes-subform'{attrs} data-subform='{html.escape(name, quote=True)}'>"
                f"<div class='notes-subform-title'>SUBFORM: {safe}</div>"
                f"{html_inner}"
                f"</div>"
            )

        # Plain text container
        if tag == "text":
            content = "".join(el.itertext())
            return html.escape(content)

        # Default: best-effort recursion
        return self._render_children(el)


def main() -> None:
    # ==== Settings ====
    form_dxl_path = Path(
        # "C:/Users/SLY/Documents/Python実験/Python - OneNote/Git/Notes_to_OneNote_python/scripts/target_form/Call2024.nsf__FORM__Call4__20260119_173539.dxl"
        "C:/Users/SLY/Documents/Python実験/Python - OneNote/Git/Notes_to_OneNote_python/scripts/target_form/synhbe29.nsf_Fm_Document_2.dxl"
    )
    search_dir = form_dxl_path.parent

    root = ET.parse(form_dxl_path).getroot()
    conv = FormToHtml(root=root, search_dir=search_dir)

    body_html = conv.render_body()

    # ---- HTML出力
    out_html = form_dxl_path.with_suffix("")
    out_html = out_html.parent / (out_html.name + "__form_template.html")
    out_html.write_text(body_html, encoding="utf-8")

    # ---- missing subforms
    out_missing = out_html.with_suffix(".missing_subforms.txt")
    if conv.missing_subforms:
        out_missing.write_text("\n".join(sorted(conv.missing_subforms)), encoding="utf-8")
    else:
        out_missing.write_text("(none)\n", encoding="utf-8")

    # ---- JSON（画面に表示された項目のみ）
    design_name = _guess_design_name(root)
    payload = {
        "design_name": design_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fields": [asdict(conv.visible_fields[k]) for k in sorted(conv.visible_fields.keys())],
        "missing_subforms": sorted(conv.missing_subforms),
        "field_count": len(conv.visible_fields),
    }

    out_json = out_html.with_suffix(".fields.json")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("HTML:", out_html)
    print("Fields JSON:", out_json)
    print("Missing subforms:", out_missing)


if __name__ == "__main__":
    main()
