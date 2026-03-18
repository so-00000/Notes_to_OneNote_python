from main.enums import DataType

# 対象データ
DATA_TYPE = DataType.SYOGAI

# DXL_DIRはDATA_TYPEに応じてdata_type_config.pyで切り替え
SLEEP_SEC = 0.2  # 連続POSTの間隔（429回避用、必要なら増やす）
