import re
import html as _html
from main.models.models import Segment

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




import html as _html

def _segment_content_html(seg, part_name: str) -> str:
    bp = seg.binary_part
    if bp.kind == "image":
        style = "max-width:100%;"
        if bp.width:
            style += f" width:{bp.width}px;"
        if bp.height:
            style += f" height:{bp.height}px;"
        return f"<img src='name:{_html.escape(part_name, quote=True)}' style='{style}'/>"

    # attachment
    fn = _html.escape(bp.filename, quote=True)
    mt = _html.escape(bp.content_type or "application/octet-stream", quote=True)
    pn = _html.escape(part_name, quote=True)
    return (
        "<div style='margin:8px 0; padding:10px; border:1px solid #e3e3e3; border-radius:10px;'>"
        f"<object data='name:{pn}' data-attachment='{fn}' type='{mt}'></object>"
        "</div>"
    )






import re

def _inject_first_segments(body_html: str, segments: list, name_prefix: str = "p") -> tuple[str, list[tuple[str, object]]]:
    """
    body_html 中の <div ... data-id='seg-001'></div> を
    <div ... data-id='seg-001'> ... </div> にしていく。
    戻り値:
      - 差し替え済み body_html
      - [(part_name, binary_part), ...]
    """
    parts: list[tuple[str, object]] = []
    out = body_html

    for i, seg in enumerate(segments, start=1):
        part_name = f"{name_prefix}{i}"  # リクエスト内で一意なら何でもOK
        content = _segment_content_html(seg, part_name)
        parts.append((part_name, seg.binary_part))

        sid = re.escape(seg.segment_id)
        # <div ... data-id="seg-001" ...></div> を、中身ありにする
        pat = re.compile(
            rf"(<div\b[^>]*\bdata-id=['\"]{sid}['\"][^>]*>)(\s*</div>)",
            re.IGNORECASE,
        )
        out, n = pat.subn(rf"\1{content}\2", out, count=1)
        # n==0 の場合：アンカーが無い（DXL→HTML 側の不整合）なのでログ出すのが吉

    return out, parts



