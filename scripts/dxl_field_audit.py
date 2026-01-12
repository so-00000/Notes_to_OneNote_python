from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# 設定（ここだけ変えればOK）
# ============================================================

BASE_DIR = Path(__file__).resolve().parent  

DXL_DIR_REL = Path("../main/target_dxl")          # ★ ここを相対パスで書く（例: data/dxl）
OUT_DIR_REL = Path("out/dxl_audit")     # ★ 出力先（例: out/dxl_audit）

DXL_DIR = (BASE_DIR / DXL_DIR_REL).resolve()
OUT_DIR = (BASE_DIR / OUT_DIR_REL).resolve()

SAMPLE_LIMIT_PER_FIELD = 5            # フィールドごとのサンプル最大数（重複除外）
SAMPLE_TEXT_LIMIT = 200               # サンプル文字列の最大長
TARGET_EXT = ".dxl"                   # 対象拡張子


# ============================================================
# 定数
# ============================================================
DXL_NS_URI = "http://www.lotus.com/dxl"
DXL = f"{{{DXL_NS_URI}}}"


# ============================================================
# データ構造
# ============================================================
@dataclass
class FieldStat:
    name: str
    types: Set[str] = field(default_factory=set)

    sample_values: List[str] = field(default_factory=list)
    sample_set: Set[str] = field(default_factory=set)

    doc_occurrences: int = 0                 # 文書単位の出現回数（同一文書で複数あっても1）
    file_set: Set[str] = field(default_factory=set)
    total_item_elements: int = 0             # item要素として見つかった回数（同一文書内複数も加算）

    is_multi_value_observed: bool = False
    max_text_len: int = 0
    child_tags: Set[str] = field(default_factory=set)

    # item属性（DXLに存在する場合に収集）
    attrs_seen: Dict[str, Set[str]] = field(default_factory=dict)

    # Form別（文書単位）
    by_form_doc_occurrences: Dict[str, int] = field(default_factory=dict)

    def add_attr(self, k: str, v: str) -> None:
        self.attrs_seen.setdefault(k, set()).add(v)

    def add_sample(self, s: str, limit: int) -> None:
        s = (s or "").strip()
        if not s:
            return
        if s in self.sample_set:
            return
        if len(self.sample_values) >= limit:
            return
        self.sample_set.add(s)
        self.sample_values.append(s)
        self.max_text_len = max(self.max_text_len, len(s))


# ============================================================
# ユーティリティ
# ============================================================
def _local_tag(tag: str) -> str:
    # "{uri}text" -> "text"
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def infer_type_and_sample(item_elem: ET.Element, sample_text_limit: int) -> Tuple[str, Optional[str], bool, Set[str]]:
    """
    Returns:
      - inferred_type: str
      - sample: Optional[str]
      - is_multi_value: bool
      - child_tags: Set[str]
    """
    children = list(item_elem)
    child_tags: Set[str] = set(_local_tag(c.tag) for c in children)

    type_attr = item_elem.get("type") or item_elem.get("class") or item_elem.get("datatype")

    if not children:
        inferred = f"Unknown(attr={type_attr})" if type_attr else "Unknown"
        return inferred, None, False, child_tags

    # list系
    list_tags = {"textlist", "numberlist", "datetimelist", "nameslist"}
    for c in children:
        t = _local_tag(c.tag)
        if t in list_tags:
            vals: List[str] = []
            for sub in list(c):
                txt = (sub.text or "").strip()
                if txt:
                    vals.append(txt)
                if len(vals) >= 5:
                    break
            sample = " | ".join(vals) if vals else None
            inferred = t.replace("list", "").upper() + "_LIST"
            if type_attr:
                inferred += f"(attr={type_attr})"
            return inferred, sample, True, child_tags

    # richtext
    for c in children:
        if _local_tag(c.tag) == "richtext":
            plain = "".join((t or "") for t in c.itertext())
            plain = " ".join(plain.split())
            if len(plain) > sample_text_limit:
                plain = plain[:sample_text_limit] + "..."
            inferred = "RICHTEXT"
            if type_attr:
                inferred += f"(attr={type_attr})"
            return inferred, (plain or None), True, child_tags

    # formula
    for c in children:
        if _local_tag(c.tag) == "formula":
            txt = (c.text or "").strip()
            if len(txt) > sample_text_limit:
                txt = txt[:sample_text_limit] + "..."
            inferred = "FORMULA"
            if type_attr:
                inferred += f"(attr={type_attr})"
            return inferred, (txt or None), False, child_tags

    # datetime
    for c in children:
        if _local_tag(c.tag) == "datetime":
            txt = (c.text or "").strip()
            attrs = []
            for k in ("date", "time", "dst", "zone"):
                v = c.get(k)
                if v:
                    attrs.append(f"{k}={v}")
            sample = txt if txt else (";".join(attrs) if attrs else None)
            inferred = "DATETIME"
            if type_attr:
                inferred += f"(attr={type_attr})"
            return inferred, sample, False, child_tags

    # number
    for c in children:
        if _local_tag(c.tag) == "number":
            txt = (c.text or "").strip()
            inferred = "NUMBER"
            if type_attr:
                inferred += f"(attr={type_attr})"
            return inferred, (txt or None), False, child_tags

    # text
    for c in children:
        if _local_tag(c.tag) == "text":
            txt = (c.text or "").strip()
            if len(txt) > sample_text_limit:
                txt = txt[:sample_text_limit] + "..."
            inferred = "TEXT"
            if type_attr:
                inferred += f"(attr={type_attr})"
            return inferred, (txt or None), False, child_tags

    # object/noteref/mime あたり
    for c in children:
        t = _local_tag(c.tag)
        if t in {"object", "noteref", "noteinfo", "mime"}:
            inferred = t.upper()
            if type_attr:
                inferred += f"(attr={type_attr})"
            keys = ["name", "unid", "noteid", "replicaid", "form"]
            parts = []
            for k in keys:
                v = c.get(k)
                if v:
                    parts.append(f"{k}={v}")
            sample = ";".join(parts) if parts else None
            return inferred, sample, True, child_tags

    # fallback
    inferred = "COMPOSITE"
    if type_attr:
        inferred += f"(attr={type_attr})"
    plain = "".join((t or "") for t in item_elem.itertext()).strip()
    if plain:
        plain = " ".join(plain.split())
        if len(plain) > sample_text_limit:
            plain = plain[:sample_text_limit] + "..."
    return inferred, (plain or None), len(children) > 1, child_tags


# ============================================================
# 走査本体
# ============================================================
def audit_dxl_dir(dxl_dir: Path) -> Tuple[Dict[str, FieldStat], Dict[str, int]]:
    field_stats: Dict[str, FieldStat] = {}

    dxl_files = sorted([p for p in dxl_dir.rglob(f"*{TARGET_EXT}") if p.is_file()])
    meta = {
        "dxl_files": len(dxl_files),
        "documents": 0,
        "items": 0,
        "parse_errors": 0,
    }

    doc_end_tags = {f"{DXL}document", f"{DXL}note"}

    for fp in dxl_files:
        rel = str(fp.relative_to(dxl_dir)).replace("\\", "/")

        fields_in_current_doc: Set[str] = set()
        current_form: Optional[str] = None

        try:
            ctx = ET.iterparse(fp, events=("end",))
        except ET.ParseError:
            meta["parse_errors"] += 1
            continue

        try:
            for event, elem in ctx:
                tag = elem.tag

                # item
                if tag == f"{DXL}item":
                    meta["items"] += 1

                    name = elem.get("name")
                    if not name:
                        elem.clear()
                        continue

                    # Form取得（文書内の item name="Form"）
                    if name == "Form":
                        _, sample, _, _ = infer_type_and_sample(elem, SAMPLE_TEXT_LIMIT)
                        if sample:
                            current_form = sample

                    stat = field_stats.get(name)
                    if stat is None:
                        stat = FieldStat(name=name)
                        field_stats[name] = stat

                    stat.file_set.add(rel)
                    stat.total_item_elements += 1

                    # item属性
                    for k, v in elem.attrib.items():
                        stat.add_attr(k, v)

                    inferred_type, sample, is_multi, child_tags = infer_type_and_sample(elem, SAMPLE_TEXT_LIMIT)
                    stat.types.add(inferred_type)
                    stat.child_tags.update(child_tags)
                    if is_multi:
                        stat.is_multi_value_observed = True
                    if sample:
                        stat.add_sample(sample, SAMPLE_LIMIT_PER_FIELD)

                    fields_in_current_doc.add(name)

                    elem.clear()
                    continue

                # 文書終端
                if tag in doc_end_tags:
                    meta["documents"] += 1
                    if fields_in_current_doc:
                        for fname in fields_in_current_doc:
                            s = field_stats[fname]
                            s.doc_occurrences += 1
                            if current_form:
                                s.by_form_doc_occurrences[current_form] = (
                                    s.by_form_doc_occurrences.get(current_form, 0) + 1
                                )

                    fields_in_current_doc.clear()
                    current_form = None
                    elem.clear()
                    continue

                # それ以外
                elem.clear()

        except ET.ParseError:
            meta["parse_errors"] += 1
            continue
        finally:
            try:
                del ctx
            except Exception:
                pass

    return field_stats, meta


# ============================================================
# 出力
# ============================================================
def write_outputs(field_stats: Dict[str, FieldStat], meta: Dict[str, int], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV（一覧）
    csv_path = out_dir / "fields_summary.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "field_name",
                "types",
                "doc_occurrences",
                "file_count",
                "total_item_elements",
                "is_multi_value_observed",
                "max_sample_text_len",
                "samples",
                "child_tags",
                "item_attrs_seen",
                "by_form_doc_occurrences_top10",
            ]
        )

        for name in sorted(field_stats.keys()):
            s = field_stats[name]
            types = " | ".join(sorted(s.types))
            samples = " || ".join(s.sample_values)
            child_tags = ",".join(sorted(s.child_tags))

            attrs_parts = []
            for k in sorted(s.attrs_seen.keys()):
                attrs_parts.append(f"{k}=" + ",".join(sorted(s.attrs_seen[k])))
            attrs_str = "; ".join(attrs_parts)

            top_forms = sorted(s.by_form_doc_occurrences.items(), key=lambda x: x[1], reverse=True)[:10]
            top_forms_str = " / ".join([f"{k}:{v}" for k, v in top_forms])

            w.writerow(
                [
                    s.name,
                    types,
                    s.doc_occurrences,
                    len(s.file_set),
                    s.total_item_elements,
                    "Y" if s.is_multi_value_observed else "N",
                    s.max_text_len,
                    samples,
                    child_tags,
                    attrs_str,
                    top_forms_str,
                ]
            )

    # JSON（全量）
    json_path = out_dir / "fields_summary.json"
    obj = {
        "meta": meta,
        "fields": {
            name: {
                "name": s.name,
                "types": sorted(s.types),
                "doc_occurrences": s.doc_occurrences,
                "file_count": len(s.file_set),
                "files": sorted(s.file_set),
                "total_item_elements": s.total_item_elements,
                "is_multi_value_observed": s.is_multi_value_observed,
                "max_sample_text_len": s.max_text_len,
                "samples": s.sample_values,
                "child_tags": sorted(s.child_tags),
                "item_attrs_seen": {k: sorted(vs) for k, vs in s.attrs_seen.items()},
                "by_form_doc_occurrences": dict(
                    sorted(s.by_form_doc_occurrences.items(), key=lambda x: x[1], reverse=True)
                ),
            }
            for name, s in field_stats.items()
        },
    }
    json_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] DXL_DIR = {DXL_DIR}")
    print(f"[OK] OUT_DIR = {OUT_DIR}")
    print(f"[OK] files={meta['dxl_files']} docs={meta['documents']} items={meta['items']} parse_errors={meta['parse_errors']}")
    print(f"[OK] wrote: {csv_path}")
    print(f"[OK] wrote: {json_path}")


def main() -> None:
    if not DXL_DIR.exists() or not DXL_DIR.is_dir():
        raise SystemExit(f"DXL_DIR not found: {DXL_DIR}")

    stats, meta = audit_dxl_dir(DXL_DIR)
    write_outputs(stats, meta, OUT_DIR)


if __name__ == "__main__":
    main()
