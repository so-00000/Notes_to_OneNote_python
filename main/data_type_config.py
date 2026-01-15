from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from main import config
from main.models.CallDb import CallDbRaw
from main.models.SyogaiDb import SyogaiDbRaw
from main.services.render_syogai_db_html import render_syogai_db_html
from main.services.render_call_db_html import render_call_db_html


@dataclass(frozen=True)
class DataTypeSettings:
    key: str
    label: str
    section_name: str
    dxl_dir: str
    title_fields: tuple[str, ...]
    rich_fields: tuple[str, ...]
    model_cls: type
    renderer: Callable[..., str]


_SETTINGS: dict[str, DataTypeSettings] = {
    "syogai": DataTypeSettings(
        key="syogai",
        label="障害DB",
        section_name="障害DB",
        dxl_dir = "target_dxl_syogai_db",
        title_fields=("DocumentNo", "Fd_Text_1"),
        rich_fields=(
            "Agenda",
            "Detail",
            "Detail_1",
            "Fd_Link_1",
            "Parmanent",
            "Reason",
            "Temporary",
        ),
        model_cls=SyogaiDbRaw,
        renderer=render_syogai_db_html,
    ),
    "call": DataTypeSettings(
        key="call",
        label="CallDB",
        section_name="CallDB",
        dxl_dir = "target_dxl_call_db",
        title_fields=("mng_no", "outline"),
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
        model_cls=CallDbRaw,
        renderer=render_call_db_html,
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
