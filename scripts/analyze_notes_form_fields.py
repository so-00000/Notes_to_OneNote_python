# analyze_notes_form_fields.py
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set, Tuple


DXL_NS = {"dxl": "http://www.lotus.com/dxl"}


@dataclass
class FieldInfo:
    field_name: str
    field_type: str
    kind: str
    allowmultivalues: str

    occurrences: int
    placed_on_form_body: bool  # <body><richtext> 配置が確認できた
    has_hidewhen: bool         # field内に hidewhen code がある
    hidden_modes: str          # 祖先（pardef/par等）の hide 属性から推定（read/edit/preview...）

    likely_displayed: str      # 最終評価（高い/条件付き/低い/不明）


def _localname(tag: str) -> str:
    # "{namespace}tag" -> "tag"
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _build_parent_map(root: ET.Element) -> Dict[ET.Element, ET.Element]:
    parent: Dict[ET.Element, ET.Element] = {}
    for p in root.iter():
        for c in list(p):
            parent[c] = p
    return parent


def _ancestor_localnames(el: ET.Element, parent: Dict[ET.Element, ET.Element]) -> List[str]:
    names: List[str] = []
    cur = el
    while cur in parent:
        cur = parent[cur]
        names.append(_localname(cur.tag))
    return names


def _ancestor_hide_modes(el: ET.Element, parent: Dict[ET.Element, ET.Element]) -> Set[str]:
    """
    Notes DXLの段落定義などに hide='read edit ...' が付くことがある。
    祖先を遡って hide 属性を集める。
    """
    modes: Set[str] = set()
    cur = el
    while True:
        hide = cur.attrib.get("hide")
        if hide:
            for tok in hide.split():
                modes.add(tok.strip())
        if cur not in parent:
            break
        cur = parent[cur]
    return modes


def _bool_has_hidewhen(field_el: ET.Element) -> bool:
    # <code event='hidewhen'> が field 要素の配下にあるか
    for code in field_el.findall(".//dxl:code", DXL_NS):
        if code.attrib.get("event", "").lower() == "hidewhen":
            return True
    return False


def _placed_on_body(field_el: ET.Element, parent: Dict[ET.Element, ET.Element]) -> bool:
    # 祖先に body / richtext があれば「画面配置されている可能性が高い」と判断
    anc = _ancestor_localnames(field_el, parent)
    return ("body" in anc) and ("richtext" in anc)


def _decide_likelihood(
    *,
    placed_on_form_body: bool,
    has_hidewhen: bool,
    hidden_modes: Set[str],
) -> str:
    # hide属性は「この段落/ブロックは特定モードで非表示」の可能性
    # read/edit 両方に入ってたらかなり怪しい
    if not placed_on_form_body:
        return "低い(画面配置なし)"
    if "read" in hidden_modes and "edit" in hidden_modes:
        return "低い(段落hideでread/edit非表示)"
    if has_hidewhen or hidden_modes:
        return "条件付き(高:配置あり/Hide-When or hide属性あり)"
    return "高い(画面配置あり)"


def analyze_form_dxl(dxl_path: Path) -> List[FieldInfo]:
    root = ET.parse(dxl_path).getroot()
    parent = _build_parent_map(root)

    # すべての <field> を拾う
    fields = root.findall(".//dxl:field", DXL_NS)

    agg: Dict[str, Dict] = {}

    for f in fields:
        name = f.attrib.get("name") or "(no-name)"
        ftype = f.attrib.get("type", "")
        kind = f.attrib.get("kind", "")
        allow_mv = f.attrib.get("allowmultivalues", "")

        placed = _placed_on_body(f, parent)
        has_hw = _bool_has_hidewhen(f)
        hide_modes = _ancestor_hide_modes(f, parent)

        if name not in agg:
            agg[name] = {
                "field_name": name,
                "field_type": ftype,
                "kind": kind,
                "allowmultivalues": allow_mv,
                "occurrences": 0,
                "placed_on_form_body": False,
                "has_hidewhen": False,
                "hidden_modes": set(),
            }

        agg[name]["occurrences"] += 1

        # type/kind は揺れがあることもあるので、空なら更新、空でなければ維持（必要ならここを強化）
        if not agg[name]["field_type"] and ftype:
            agg[name]["field_type"] = ftype
        if not agg[name]["kind"] and kind:
            agg[name]["kind"] = kind
        if not agg[name]["allowmultivalues"] and allow_mv:
            agg[name]["allowmultivalues"] = allow_mv

        agg[name]["placed_on_form_body"] = agg[name]["placed_on_form_body"] or placed
        agg[name]["has_hidewhen"] = agg[name]["has_hidewhen"] or has_hw
        agg[name]["hidden_modes"].update(hide_modes)

    # FieldInfoに整形
    out: List[FieldInfo] = []
    for name, d in agg.items():
        hidden_modes_set: Set[str] = d["hidden_modes"]
        hidden_modes_str = " ".join(sorted(hidden_modes_set))

        likely = _decide_likelihood(
            placed_on_form_body=d["placed_on_form_body"],
            has_hidewhen=d["has_hidewhen"],
            hidden_modes=hidden_modes_set,
        )

        out.append(
            FieldInfo(
                field_name=d["field_name"],
                field_type=d["field_type"],
                kind=d["kind"],
                allowmultivalues=d["allowmultivalues"],
                occurrences=d["occurrences"],
                placed_on_form_body=d["placed_on_form_body"],
                has_hidewhen=d["has_hidewhen"],
                hidden_modes=hidden_modes_str,
                likely_displayed=likely,
            )
        )

    # 名前順で安定ソート
    out.sort(key=lambda x: x.field_name.lower())
    return out


def write_csv(rows: List[FieldInfo], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "field_name",
                "field_type",
                "kind",
                "allowmultivalues",
                "occurrences",
                "placed_on_form_body",
                "has_hidewhen",
                "hidden_modes",
                "likely_displayed",
            ],
            quoting=csv.QUOTE_ALL,
        )
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def main() -> None:
    # ★ここを差し替えれば別フォームにも使える
    dxl_path = Path(r"C:\Users\SLY\Documents\Python実験\Python - OneNote\Git\Notes_to_OneNote_python\scripts\target_form\Call2024.nsf__FORM__Call4__20260119_173539.dxl")

    rows = analyze_form_dxl(dxl_path)

    out_csv = dxl_path.with_suffix("")  # .dxl を外す
    out_csv = out_csv.parent / (out_csv.name + "__fields.csv")

    write_csv(rows, out_csv)

    # ざっくりサマリ
    total = len(rows)
    high = sum(1 for r in rows if r.likely_displayed.startswith("高い"))
    cond = sum(1 for r in rows if r.likely_displayed.startswith("条件付き"))
    low = sum(1 for r in rows if r.likely_displayed.startswith("低い"))
    noname = sum(1 for r in rows if r.field_name == "(no-name)")

    print(f"DXL: {dxl_path}")
    print(f"fields(unique): {total} / high={high} / conditional={cond} / low={low} / no-name={noname}")
    print(f"CSV: {out_csv}")


if __name__ == "__main__":
    main()
