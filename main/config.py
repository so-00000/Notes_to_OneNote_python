NOTEBOOK_NAME = "TEST_Notes_to_OneNote"
SECTION_NAME = "障害DB"
# SECTION_NAME = "CallDB"

DXL_DIR = "target_dxl"
TITLE_COLUMN = "DocumentNo"  # ページタイトルに使う列名
SLEEP_SEC = 0.2  # 連続POSTの間隔（429回避用、必要なら増やす）

# RichText（画像 / リンク / 表などを拾う可能性のあるフィールド）
# タスク：動的にする
RICH_FIELDS = [
    "Agenda",
    "Detail",
    "Detail_1",
    "Fd_Link_1",
    "Parmanent",
    "Reason",
    "Temporary",
]