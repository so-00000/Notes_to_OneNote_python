import json
from pathlib import Path
from typing import Set

# ------------------------------------------------------------
# fields.json（画面項目定義）からフィールド名を抽出
# ------------------------------------------------------------
def load_visible_field_names(fields_json_path: str | Path) -> Set[str]:
    """
    fields.json の fields[] から name を集めて返す（画面表示対象のフィールド名セット）。
    """
    p = Path(fields_json_path)
    obj = json.loads(p.read_text(encoding="utf-8"))
    return {f.get("name") for f in obj.get("fields", []) if f.get("name")}


def load_richtext_field_names(fields_json_path: str | Path) -> Set[str]:
    """
    fields.json の fields[] から type == 'richtext' の name を集めて返す。
    """
    p = Path(fields_json_path)
    obj = json.loads(p.read_text(encoding="utf-8"))

    out: Set[str] = set()
    for f in obj.get("fields", []):
        name = f.get("name")
        if not name:
            continue
        if (f.get("type") or "").lower() == "richtext":
            out.add(name)
    return out