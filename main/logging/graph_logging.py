from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional


REDACTED = "***REDACTED***"


def mask_headers(headers: Mapping[str, str]) -> Dict[str, str]:
    """
    ヘッダーをログ出力するためにマスクする。
    - Authorization / Cookie などは必ず秘匿する。
    """
    masked = dict(headers)

    for k in list(masked.keys()):
        lk = k.lower()
        if lk in ("authorization", "cookie", "set-cookie", "x-authorization"):
            masked[k] = REDACTED

    return masked


def truncate_text(text: str, limit: int = 2000) -> str:
    """ログ肥大化防止のための切り詰め。"""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(truncated {len(text) - limit} chars)"


def safe_json_preview(obj: Any, limit: int = 2000) -> str:
    """
    JSON（dict/list等）をログ用に短く整形する。
    """
    if obj is None:
        return ""
    try:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
        return truncate_text(s, limit=limit)
    except Exception:
        return truncate_text(str(obj), limit=limit)


def summarize_multipart_files(files: Any) -> list[dict]:
    """
    requests の files（multipart）を“中身無し”で要約する。
    - バイナリを丸ごとログに出さない
    - パート名/ファイル名/Content-Type/サイズ程度に留める
    """
    if not files:
        return []

    # 想定: dict[name] = (filename, content, content_type)
    out: list[dict] = []
    try:
        items = files.items() if hasattr(files, "items") else list(files)
    except Exception:
        return [{"warning": "files could not be summarized"}]

    for name, value in items:
        try:
            # value: (filename, content, content_type) を想定
            filename = value[0] if len(value) > 0 else None
            content = value[1] if len(value) > 1 else None
            content_type = value[2] if len(value) > 2 else None

            size = None
            if isinstance(content, (bytes, bytearray)):
                size = len(content)
            elif hasattr(content, "read"):
                # file-like はサイズ不明（読み出してはいけない）
                size = None
            elif isinstance(content, str):
                # 文字列は危険なので長さだけ
                size = len(content)

            out.append(
                {
                    "part": str(name),
                    "filename": str(filename) if filename is not None else None,
                    "content_type": str(content_type) if content_type is not None else None,
                    "size": size,
                }
            )
        except Exception:
            out.append({"part": str(name), "warning": "failed to summarize this part"})

    return out


def summarize_request_kwargs(request_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    _session.request(...) に渡す kwargs をログ用に安全に要約する。
    """
    summary: Dict[str, Any] = {}

    if "params" in request_kwargs and request_kwargs["params"] is not None:
        summary["params"] = request_kwargs["params"]

    if "json" in request_kwargs and request_kwargs["json"] is not None:
        summary["json"] = safe_json_preview(request_kwargs["json"])

    if "data" in request_kwargs and request_kwargs["data"] is not None:
        data = request_kwargs["data"]
        if isinstance(data, (bytes, bytearray)):
            summary["data_bytes"] = len(data)
        else:
            summary["data_preview"] = truncate_text(str(data), limit=500)

    if "files" in request_kwargs and request_kwargs["files"] is not None:
        summary["multipart_parts"] = summarize_multipart_files(request_kwargs["files"])

    if "timeout" in request_kwargs and request_kwargs["timeout"] is not None:
        summary["timeout"] = request_kwargs["timeout"]

    return summary
