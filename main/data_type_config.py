from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from main import config
# from main.models.CallDb import CallDbRaw
# from main.models.SyogaiDb import SyogaiDbRaw
# from main.renderers.syogai.render_syogai_db_html import render_syogai_db_html
# from main.renderers.call.render_call_db_html import render_call_db_html


@dataclass(frozen=True)
class DataTypeSettings:
    key: str
    label: str
    section_name: str
    dxl_dir: str
    template_html_path: str
    fields_json_path: str
    title_field: tuple[str, ...]
    rich_fields: tuple[str, ...]
    # model_cls: type
    # renderer: Callable[..., str]


_SETTINGS: dict[str, DataTypeSettings] = {
    "syogai": DataTypeSettings(
        key="syogai",
        label="障害DB",
        section_name="障害DB",
        dxl_dir="resources/forms/synhbe29.nsf_Fm_Document_2",
        template_html_path=(
            "templates/synhbe29.nsf_Fm_Document_2/"
            "synhbe29.nsf_Fm_Document_2__form_template.html"
        ),
        fields_json_path=(
            "resources/forms/synhbe29.nsf_Fm_Document_2/"
            "synhbe29.nsf_Fm_Document_2__form_template.fields.json"
        ),
        title_field="Fd_Text_1",
        rich_fields=(
            "Agenda",
            "Detail",
            "Detail_1",
            "Fd_Link_1",
            "Parmanent",
            "Reason",
            "Temporary",
        ),
        # model_cls=SyogaiDbRaw,
        # renderer=render_syogai_db_html,
    ),
    "call": DataTypeSettings(
        key="call",
        label="CallDB",
        section_name="CallDB",
        dxl_dir="resources/forms/Call2024.nsf__FORM__Call4__20260119_173539",
        template_html_path=(
            "templates/Call2024.nsf__FORM__Call4__20260119_173539/"
            "Call2024.nsf__FORM__Call4__20260119_173539__form_template.html"
        ),
        fields_json_path=(
            "resources/forms/Call2024.nsf__FORM__Call4__20260119_173539/"
            "Call2024.nsf__FORM__Call4__20260119_173539__form_template.fields.json"
        ),
        title_field="outline",
        rich_fields=(
            # "Agenda",
            # "Detail",
            # "Detail_1",
            # "Fd_Link_1",
            # "Parmanent",
            # "Reason",
            # "Temporary",
            "body",
            "body_1",
        ),
        # model_cls=CallDbRaw,
        # renderer=render_call_db_html,
    ),
}


def _normalize_data_type(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = raw.lower()
    if normalized in {"1", "syogai", "障害db", "障害"}:
        return "syogai"
    if normalized in {"2", "call", "calldb", "call db"}:
        return "call"
    return normalized


def get_data_type_settings() -> DataTypeSettings:
    key = _normalize_data_type(config.DATA_TYPE)
    if key in _SETTINGS:
        return _SETTINGS[key]
    available = ", ".join(sorted(_SETTINGS.keys()))
    raise ValueError(f"Unknown DATA_TYPE: {config.DATA_TYPE!r}. Available: {available}")
