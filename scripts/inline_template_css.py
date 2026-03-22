from __future__ import annotations

import argparse
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_RULE_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.DOTALL)
STYLE_TAG_RE = re.compile(r"<style\b[^>]*>(?P<css>.*?)</style>", re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r"<!--.*?-->|<![^>]*>|</?[A-Za-z][^>]*?>", re.DOTALL)
ATTR_RE = re.compile(
    r"""([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s/>]+)))?""",
    re.DOTALL,
)

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(frozen=True)
class CssRule:
    selector_steps: tuple[frozenset[str], ...]
    declarations: tuple[tuple[str, str], ...]
    specificity: int
    order: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTML template の外部 CSS を各要素の inline style に展開します。"
    )
    parser.add_argument("html", type=Path, help="入力 HTML ファイル")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="出力 HTML ファイル。省略時は入力と同じ場所に .inlined.html を作成",
    )
    parser.add_argument(
        "--remove-class",
        action="store_true",
        help="inline 化後に class 属性を削除",
    )
    return parser.parse_args()


def load_css_and_strip_refs(html_text: str, html_path: Path) -> tuple[str, str]:
    css_parts: list[str] = []

    def replace_style(match: re.Match[str]) -> str:
        css_parts.append(match.group("css"))
        return ""

    html_wo_style = STYLE_TAG_RE.sub(replace_style, html_text)

    def replace_link(match: re.Match[str]) -> str:
        tag = match.group(0)
        attrs = parse_attrs(tag)
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "")
        if rel != "stylesheet" or not href:
            return tag
        css_path = (html_path.parent / href).resolve()
        css_parts.append(css_path.read_text(encoding="utf-8"))
        return ""

    html_wo_refs = re.sub(
        r"<link\b[^>]*>",
        replace_link,
        html_wo_style,
        flags=re.IGNORECASE,
    )
    return html_wo_refs, "\n".join(css_parts)


def parse_css(css_text: str) -> list[CssRule]:
    cleaned = CSS_COMMENT_RE.sub("", css_text)
    rules: list[CssRule] = []
    order = 0
    for match in CSS_RULE_RE.finditer(cleaned):
        selectors = [s.strip() for s in match.group("selectors").split(",") if s.strip()]
        declarations = parse_declarations(match.group("body"))
        if not declarations:
            continue
        for selector in selectors:
            steps = parse_selector(selector)
            if not steps:
                continue
            specificity = sum(len(step) for step in steps)
            rules.append(
                CssRule(
                    selector_steps=tuple(steps),
                    declarations=tuple(declarations),
                    specificity=specificity,
                    order=order,
                )
            )
            order += 1
    return rules


def parse_selector(selector: str) -> list[frozenset[str]]:
    steps: list[frozenset[str]] = []
    for part in selector.split():
        classes = re.findall(r"\.([A-Za-z0-9_-]+)", part)
        if not classes:
            return []
        steps.append(frozenset(classes))
    return steps


def parse_declarations(body: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for chunk in body.split(";"):
        if ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        prop = prop.strip()
        value = value.strip()
        if prop and value:
            out.append((prop, value))
    return out


def parse_attrs(tag_text: str) -> OrderedDict[str, str]:
    inner = tag_text.strip()[1:-1].strip()
    if inner.startswith("/"):
        inner = inner[1:].lstrip()
    if " " in inner:
        _, inner = inner.split(" ", 1)
    else:
        inner = ""
    attrs: OrderedDict[str, str] = OrderedDict()
    for name, dq, sq, bare in ATTR_RE.findall(inner):
        value = dq or sq or bare or ""
        attrs[name] = value
    return attrs


def serialize_attrs(attrs: OrderedDict[str, str]) -> str:
    if not attrs:
        return ""
    parts: list[str] = []
    for name, value in attrs.items():
        escaped = value.replace('"', "&quot;")
        parts.append(f'{name}="{escaped}"')
    return " " + " ".join(parts)


def build_style(
    attrs: OrderedDict[str, str],
    ancestors: list[frozenset[str]],
    rules: list[CssRule],
) -> str:
    class_names = frozenset(filter(None, attrs.get("class", "").split()))
    if not class_names:
        existing = attrs.get("style", "")
        return normalize_style(existing)

    applicable = [
        rule
        for rule in rules
        if selector_matches(rule.selector_steps, ancestors, class_names)
    ]
    applicable.sort(key=lambda rule: (rule.specificity, rule.order))

    merged: OrderedDict[str, str] = OrderedDict()
    for rule in applicable:
        for prop, value in rule.declarations:
            merged[prop] = value
    for prop, value in parse_declarations(attrs.get("style", "")):
        merged[prop] = value
    return serialize_style(merged)


def selector_matches(
    selector_steps: Iterable[frozenset[str]],
    ancestors: list[frozenset[str]],
    self_classes: frozenset[str],
) -> bool:
    steps = list(selector_steps)
    if not steps:
        return False
    if not steps[-1].issubset(self_classes):
        return False

    anc_index = len(ancestors) - 1
    for step in reversed(steps[:-1]):
        while anc_index >= 0 and not step.issubset(ancestors[anc_index]):
            anc_index -= 1
        if anc_index < 0:
            return False
        anc_index -= 1
    return True


def serialize_style(style_map: OrderedDict[str, str]) -> str:
    return " ".join(f"{prop}: {value};" for prop, value in style_map.items())


def normalize_style(style_text: str) -> str:
    return serialize_style(OrderedDict(parse_declarations(style_text)))


def inline_css(html_text: str, rules: list[CssRule], remove_class: bool) -> str:
    out: list[str] = []
    stack: list[tuple[str, frozenset[str]]] = []
    pos = 0

    for match in TAG_RE.finditer(html_text):
        out.append(html_text[pos:match.start()])
        tag = match.group(0)

        if tag.startswith("<!--") or tag.startswith("<!"):
            out.append(tag)
            pos = match.end()
            continue

        closing = tag.startswith("</")
        tag_name_match = re.match(r"</?\s*([A-Za-z0-9:_-]+)", tag)
        if not tag_name_match:
            out.append(tag)
            pos = match.end()
            continue
        tag_name = tag_name_match.group(1).lower()

        if closing:
            out.append(tag)
            while stack:
                open_tag_name, _ = stack.pop()
                if open_tag_name == tag_name:
                    break
            pos = match.end()
            continue

        attrs = parse_attrs(tag)
        ancestors = [classes for _, classes in stack]
        style_text = build_style(attrs, ancestors, rules)
        if style_text:
            attrs["style"] = style_text
        elif "style" in attrs:
            del attrs["style"]

        class_names = frozenset(filter(None, attrs.get("class", "").split()))
        if tag_name == "table" and "notes-table" in class_names:
            attrs.setdefault("width", "800")
            attrs.setdefault("border", "1")
            attrs.setdefault("cellspacing", "0")
            attrs.setdefault("cellpadding", "0")

        if remove_class and "class" in attrs:
            del attrs["class"]

        self_closing = tag.endswith("/>") or tag_name in VOID_TAGS
        rebuilt = f"<{tag_name}{serialize_attrs(attrs)}{' /' if tag.endswith('/>') else ''}>"
        out.append(rebuilt)

        if not self_closing:
            stack.append((tag_name, class_names))

        pos = match.end()

    out.append(html_text[pos:])
    return "".join(out)


def default_output_path(html_path: Path) -> Path:
    if html_path.parent.name == "before_inline":
        return html_path.parent.parent / f"{html_path.stem}.inlined{html_path.suffix}"
    return html_path.with_name(f"{html_path.stem}.inlined{html_path.suffix}")


def resolve_input_html(html_path: Path) -> Path:
    resolved = html_path.resolve()
    if resolved.exists():
        return resolved

    before_inline_candidate = resolved.parent / "before_inline" / resolved.name
    if before_inline_candidate.exists():
        return before_inline_candidate.resolve()

    raise FileNotFoundError(f"HTML file not found: {html_path}")


def main() -> None:
    args = parse_args()
    html_path = resolve_input_html(args.html)
    output_path = (args.output or default_output_path(html_path)).resolve()

    html_text = html_path.read_text(encoding="utf-8")
    stripped_html, css_text = load_css_and_strip_refs(html_text, html_path)
    rules = parse_css(css_text)
    inlined_html = inline_css(stripped_html, rules, remove_class=args.remove_class)

    output_path.write_text(inlined_html, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
