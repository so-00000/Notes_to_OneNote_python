from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logging(
    *,
    log_dir: str = "logs",
    level: str = "INFO",
    filename: str = "app.log",
    max_bytes: int = 5 * 1024 * 1024,  # 5MB
    backup_count: int = 3,
) -> None:
    """
    アプリ全体のlogging設定（コンソール + ファイル）を行う。

    - 既にハンドラが設定済みの場合は二重設定を避ける。
    - ログファイルはローテーションする（サイズ上限 + 世代数）。
    """
    root = logging.getLogger()
    if root.handlers:
        return  # 二重設定を避ける

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = os.path.join(log_dir, filename)

    # フォーマット（必要なら project 用に変えてOK）
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    # File (rotating)
    fh = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(ch)
    root.addHandler(fh)
