from __future__ import annotations

from dataclasses import dataclass
from main import config


@dataclass(frozen=True)
class DataTypeSettings:
    key: str
    label: str
    section_name: str
    view_name: str
    dxl_dir: str
    template_html_path: str
    fields_json_path: str
    title_field: tuple[str, ...]


_SETTINGS: dict[str, DataTypeSettings] = {

    "syogai": DataTypeSettings(
        key="syogai",
        label="障害DB",
        section_name="障害DB",
        view_name="VwSyogai_11ALL",
        dxl_dir="1_target_dxl/Fm_Document_2/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_2/",
        fields_json_path= "resources/forms/synhbe29.nsf/Fm_Document_2/",
        title_field="Fd_Text_1",
    ),

    "data_patch": DataTypeSettings(
        key="data_patch",
        label="データ強制変更DB",
        section_name="データ強制変更DB",
        view_name="VwData_Patch_1_3ALL",
        dxl_dir="1_target_dxl/Fm_Document_3/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_3/",
        fields_json_path= "resources/forms/synhbe29.nsf/Fm_Document_3/",
        title_field="Fd_Text_1",
    ),

    "hosyu": DataTypeSettings(
        key="hosyu",
        label="保守DB",
        section_name="保守DB",
        view_name="VwHosyu_1",
        dxl_dir="1_target_dxl/Fm_Document_5/",
        template_html_path="resources/templates/synhbe29.nsf/Fm_Document_5/",
        fields_json_path= "resources/forms/synhbe29.nsf/Fm_Document_5/",
        title_field="Fd_Text_1",
    ),

    "call2024": DataTypeSettings(
        key="call2024",
        label="CallDB2024",
        section_name="CallDB2024",
        view_name="2024_基本担当者別日付別全ｺｰﾙ",
        dxl_dir="1_target_dxl/Call2024/",
        template_html_path="resources/templates/call_gen/Call4/",
        fields_json_path="resources/forms/call_gen/Call4/",
        title_field="outline",
    ),
}


def _normalize_data_type(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = raw.lower()
    if normalized in {"2", "syogai", "障害db", "障害 db"}:
        return "syogai"
    if normalized in {"3", "data_patch", "データ強制変更db", "データ強制変更 db"}:
        return "data_patch"
    if normalized in {"5", "hosyu", "保守db", "保守 db"}:
        return "hosyu"
    if normalized in {"2024", "call2024", "calldb2024", "call db2024"}:
        return "call2024"


    return normalized


def get_data_type_settings() -> DataTypeSettings:
    key = _normalize_data_type(config.DATA_TYPE)
    if key in _SETTINGS:
        return _SETTINGS[key]
    available = ", ".join(sorted(_SETTINGS.keys()))
    raise ValueError(f"Unknown DATA_TYPE: {config.DATA_TYPE!r}. Available: {available}")
