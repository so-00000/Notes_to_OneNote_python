from __future__ import annotations

from pathlib import Path

from main import config
from main.data_type_config import get_data_type_settings
from main.find_id import find_notebook_id, find_section_id
from main.models import AppSettings
from main.services.graph_auth import build_access_token_provider
from main.services.graph_client import GraphClient


def _config_str(name: str) -> str:
    value = getattr(config, name, "")
    return str(value or "").strip()


def resolve_dxl_dir(config_value: str) -> Path:
    if not config_value or not str(config_value).strip():
        raise RuntimeError("DXL_DIR is empty. Set it in config.py")

    dxl_path = Path(config_value)
    if dxl_path.is_absolute():
        return dxl_path

    base_dir = Path(__file__).resolve().parents[1]
    return (base_dir / dxl_path).resolve()


def load_app_settings() -> AppSettings:
    data_type_settings = get_data_type_settings()
    notebook_name = _config_str("NOTEBOOK_NAME")
    section_name = _config_str("SECTION_NAME")
    if not notebook_name:
        raise RuntimeError("NOTEBOOK_NAME is empty. Set it in config.py")

    dxl_dir = resolve_dxl_dir(data_type_settings.dxl_dir)
    if not dxl_dir.exists():
        raise RuntimeError(f"DXL_DIR not found: {dxl_dir}")
    if not dxl_dir.is_dir():
        raise RuntimeError(f"DXL_DIR is not a directory: {dxl_dir}")

    return AppSettings(
        notebook_name=notebook_name,
        section_name=section_name,
        view_name=data_type_settings.view_name,
        dxl_dir=dxl_dir,
        sleep_sec=float(getattr(config, "SLEEP_SEC", 0) or 0),
    )


def build_graph_client(settings: AppSettings) -> GraphClient:
    max_requests_per_run = getattr(config, "MAX_REQUESTS_PER_RUN", None)
    max_requests = int(max_requests_per_run) if max_requests_per_run else None
    return GraphClient(
        build_access_token_provider(),
        max_requests_per_run=max_requests,
    )


def resolve_target_notebook_id(client: GraphClient, settings: AppSettings) -> str:
    return find_notebook_id(client, settings.notebook_name)


def resolve_target_section_name(settings: AppSettings) -> str:
    return settings.section_name


def resolve_target_section_id(
    client: GraphClient,
    settings: AppSettings,
    notebook_id: str,
    section_name: str | None = None,
) -> str:
    resolved_section_name = (section_name or "").strip() or resolve_target_section_name(settings)
    if not resolved_section_name:
        raise RuntimeError("SECTION_NAME is empty. Set it in config.py or pass section_name.")
    return find_section_id(client, notebook_id, resolved_section_name)
