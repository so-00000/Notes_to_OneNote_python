from __future__ import annotations

import html
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set

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


def _find_body_richtext(root: ET.Element) -> Optional[ET.Element]:
    body = root.find("dxl:body", DXL_NS)
    if body is None:
        return None
    return body.find("dxl:richtext", DXL_NS)


def _guess_design_name(root: ET.Element) -> str:
    # Form/Subform design notes often have name/alias
    name = root.attrib.get("name") or ""
    alias = root.attrib.get("alias") or ""
    if name and alias and name != alias:
        return f"{name} ({alias})"
    return name or alias or "(unknown)"


def _find_subform_dxl(subform_name: str, search_dir: Path) -> Optional[Path]:
    """Try to locate a subform design DXL file near the form DXL."""
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


class FormToHtml:
    """Best-effort DXL richtext -> simple HTML."""

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

    def render_body(self) -> str:
        rich = _find_body_richtext(self.root)
        if rich is None:
            return "<!-- body/richtext not found -->"

        design_name = _guess_design_name(self.root)
        parts: List[str] = []

        # Minimal CSS: OneNote is picky; keep it simple.
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
            ".notes-form .notes-button{background:#e5e5e5;border:1px solid #777;border-radius:2px;padding:2px 10px;font-size:10.5pt;}"
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
                inner = "&nbsp;"
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
            return f"<table{attrs}>{self._render_children(el)}</table>"
        if tag == "tablerow":
            attrs = self._data_attrs_common(el)
            return f"<tr{attrs}>{self._render_children(el)}</tr>"
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

        # Field placeholder
        if tag == "field":
            name = el.attrib.get("name", "")
            ftype = el.attrib.get("type", "")
            kind = el.attrib.get("kind", "")
            amv = el.attrib.get("allowmultivalues", "")

            attrs = [
                "class='notes-field'",
                f"data-field='{html.escape(name, quote=True)}'",
            ]
            if ftype:
                attrs.append(f"data-type='{html.escape(ftype, quote=True)}'")
            if kind:
                attrs.append(f"data-kind='{html.escape(kind, quote=True)}'")
            if amv:
                attrs.append(
                    f"data-allowmultivalues='{html.escape(amv, quote=True)}'"
                )

            common = self._data_attrs_common(el)
            label = html.escape(name)
            return f"<span {' '.join(attrs)}{common}>{{{{{label}}}}}</span>"

        if tag == "sharedfieldref":
            name = el.attrib.get("name", "")
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
                # cycle protection
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

            # Parse subform DXL and render its body
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

            # merge missing lists upward
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
    # ==== Settings (edit if needed) ====
    form_dxl_path = Path("C:/Users/SLY/Documents/Python実験/Python - OneNote/Git/Notes_to_OneNote_python/scripts/target_form/Call2024.nsf__FORM__Call4__20260119_173539.dxl")
    search_dir = form_dxl_path.parent  # subform dxl search location

    root = ET.parse(form_dxl_path).getroot()
    conv = FormToHtml(root=root, search_dir=search_dir)
    body_html = conv.render_body()

    out_html = form_dxl_path.with_suffix("")
    out_html = out_html.parent / (out_html.name + "__form_template.html")
    out_html.write_text(body_html, encoding="utf-8")

    out_missing = out_html.with_suffix(".missing_subforms.txt")
    if conv.missing_subforms:
        out_missing.write_text("\n".join(sorted(conv.missing_subforms)), encoding="utf-8")
    else:
        out_missing.write_text("(none)\n", encoding="utf-8")

    print("HTML:", out_html)
    print("Missing subforms:", out_missing)


if __name__ == "__main__":
    main()
