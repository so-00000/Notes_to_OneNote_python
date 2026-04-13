from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Protocol, Sequence

from main import config

try:
    import msal
except ImportError:  # pragma: no cover
    msal = None


class AccessTokenProvider(Protocol):
    def get_access_token(self, *, force_refresh: bool = False) -> str: ...


def _config_str(name: str, default: str = "") -> str:
    value = getattr(config, name, default)
    return str(value or "").strip()


def _config_scopes() -> list[str]:
    raw = getattr(config, "GRAPH_SCOPES", None)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []

    scopes: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            scopes.append(text)
    return scopes


class StaticAccessTokenProvider:
    def __init__(self, access_token: str) -> None:
        token = str(access_token or "").strip()
        if not token:
            raise RuntimeError("ACCESS_TOKEN is empty.")
        self._access_token = token

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        return self._access_token


class DeviceCodeAccessTokenProvider:
    def __init__(
        self,
        *,
        client_id: str,
        tenant_id: str,
        scopes: Sequence[str],
        cache_path: Path | None = None,
    ) -> None:
        if msal is None:
            raise RuntimeError(
                "msal is not installed. Run 'pip install msal' in this environment."
            )

        self._client_id = str(client_id or "").strip()
        self._tenant_id = str(tenant_id or "").strip()
        self._scopes = [str(scope or "").strip() for scope in scopes if str(scope or "").strip()]
        if not self._client_id:
            raise RuntimeError("GRAPH_CLIENT_ID is empty. Set it in main/config.py")
        if not self._tenant_id:
            raise RuntimeError("GRAPH_TENANT_ID is empty. Set it in main/config.py")
        if not self._scopes:
            raise RuntimeError("GRAPH_SCOPES is empty. Set it in main/config.py")

        self._cache_path = cache_path or (
            Path(__file__).resolve().parents[1] / "ignore_git" / "msal_token_cache.json"
        )
        self._cache = msal.SerializableTokenCache()
        self._lock = Lock()
        self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=self._client_id,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            token_cache=self._cache,
        )

    def _load_cache(self) -> None:
        if not self._cache_path.exists():
            return
        data = self._cache_path.read_text(encoding="utf-8").strip()
        if data:
            self._cache.deserialize(data)

    def _save_cache(self) -> None:
        if not self._cache.has_state_changed:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    def _extract_access_token(self, result: dict) -> str:
        access_token = str(result.get("access_token") or "").strip()
        if access_token:
            self._save_cache()
            return access_token

        error = str(result.get("error") or "").strip()
        description = str(result.get("error_description") or "").strip()
        detail = description or json.dumps(result, ensure_ascii=False)
        raise RuntimeError(f"Graph token acquisition failed: {error or 'unknown_error'}: {detail}")

    def _acquire_device_code_token(self) -> str:
        flow = self._app.initiate_device_flow(scopes=self._scopes)
        if "user_code" not in flow:
            raise RuntimeError(
                "Failed to start device code flow: "
                f"{json.dumps(flow, ensure_ascii=False)}"
            )

        message = str(flow.get("message") or "").strip()
        if message:
            print(message)

        result = self._app.acquire_token_by_device_flow(flow)
        return self._extract_access_token(result)

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        with self._lock:
            account = None
            accounts = self._app.get_accounts()
            if accounts:
                account = accounts[0]

            if account is not None and not force_refresh:
                result = self._app.acquire_token_silent(self._scopes, account=account)
                if result and result.get("access_token"):
                    return self._extract_access_token(result)

            if account is not None:
                result = self._app.acquire_token_silent_with_error(
                    self._scopes,
                    account=account,
                    force_refresh=True,
                )
                if result and result.get("access_token"):
                    return self._extract_access_token(result)

            return self._acquire_device_code_token()


def build_access_token_provider() -> AccessTokenProvider:
    client_id = _config_str("GRAPH_CLIENT_ID")
    tenant_id = _config_str("GRAPH_TENANT_ID")
    scopes = _config_scopes()
    if client_id and tenant_id:
        return DeviceCodeAccessTokenProvider(
            client_id=client_id,
            tenant_id=tenant_id,
            scopes=scopes,
        )

    from main.ignore_git import token

    return StaticAccessTokenProvider(token.ACCESS_TOKEN)
