from main.enums import DataType

# 対象データ
# DATA_TYPE = DataType.SYOGAI
# DATA_TYPE = DataType.CALL2024
DATA_TYPE = DataType.DATA_PATCH

# 対象の OneNote ノートブック名
# NOTEBOOK_NAME = "障害DB"
NOTEBOOK_NAME = "データ強制変更"
# NOTEBOOK_NAME = "UserCall"

# 対象の OneNote セクション名
# SECTION_NAME = "障害DB_2024"
SECTION_NAME = "データ強制変更_2017"
# SECTION_NAME = "UserCall_2024"

# DXL_DIRはDATA_TYPEに応じてdata_type_config.pyで切り替え
SLEEP_SEC = 0.2  # 連続POSTの間隔（429回避用、必要なら増やす）
