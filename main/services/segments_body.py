import re
import html as _html
from ..models.models import Segment

def _segment_to_html(seg: Segment, *, part_name: str) -> str:

    # 画像データのHTML変換
    if seg.binary_part.kind == "image":
        style = "max-width:100%;"
        if seg.binary_part.width:
            style += f" width:{seg.binary_part.width}px;"
        if seg.binary_part.height:
            style += f" height:{seg.binary_part.height}px;"
        return (
            "<div style='margin:8px 0;'>"
            f"<img src='name:{_html.escape(part_name, quote=True)}' style='{style}'/>"
            "</div>"
        )

    # 添付ファイルデータのHTML変換
    fn = _html.escape(seg.binary_part.filename, quote=True)
    mt = _html.escape(seg.binary_part.content_type or "application/octet-stream", quote=True)
    pn = _html.escape(part_name, quote=True)
    return (
        "<div style='margin:8px 0; padding:10px; border:1px solid #e3e3e3; "
        "border-radius:10px; background:#fff;'>"
        f"<object data='name:{pn}' data-attachment='{fn}' type='{mt}'></object>"
        "</div>"
    )



def _inject_segments_into_body(body_html: str, seg_to_inner_html: dict[str, str]) -> str:
    # <div ... data-id='seg-001' ...></div> を <div ...>INNER</div> にする
    # id属性は消される可能性があるので data-id を軸にする
    def repl(m: re.Match) -> str:
        seg_id = m.group("segid")
        inner = seg_to_inner_html.get(seg_id)
        if inner is None:
            return m.group(0)  # 送らないセグメントはそのまま（空div）
        # 元のdiv開始タグを再利用して中身だけ入れる
        open_tag = m.group("opentag")
        return f"{open_tag}{inner}</div>"

    # data-id="..." を含む空divだけ対象にする
    pattern = re.compile(
        r"(?P<opentag><div\b[^>]*\bdata-id=['\"](?P<segid>[^'\"]+)['\"][^>]*>)\s*</div>",
        re.IGNORECASE,
    )
    return pattern.sub(repl, body_html)
