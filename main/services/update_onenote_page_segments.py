import json
from urllib.parse import quote

def _build_update_multipart(self, segments: list) -> dict:
    """
    multipart の files(data_parts) 用 dict を作る。
    - Commands: JSON array
    - その他: バイナリ part
    """
    commands = []
    data_parts = {}

    # Commands パート
    # action=append は data-id(#xxx) でターゲット指定できる :contentReference[oaicite:4]{index=4}
    for idx, seg in enumerate(segments, start=1):
        part_name = f"u{idx}"  # update用 part名
        content = _segment_content_html(seg, part_name)

        commands.append(
            {
                "target": f"#{seg.segment_id}",
                "action": "append",
                "position": "after",  # 省略可（デフォ after）:contentReference[oaicite:5]{index=5}
                "content": content,
            }
        )

        bp = seg.binary_part
        data_parts[part_name] = (bp.filename, bp.data, bp.content_type)

    data_parts["Commands"] = ("commands.json", json.dumps(commands, ensure_ascii=False), "application/json")
    return data_parts


def update_onenote_page_segments(self, *, page_id: str, segments: list) -> None:
    url = f"https://graph.microsoft.com/v1.0/me/onenote/pages/{quote(page_id)}/content"
    data_parts = self._build_update_multipart(segments)
    r = self._request_multipart("PATCH", url, data_parts=data_parts)
    # 成功は 204 :contentReference[oaicite:6]{index=6}
    if r.status_code != 204:
        r.raise_for_status()
