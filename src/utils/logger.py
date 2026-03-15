"""ログ設定 — 日次ファイル + コンソール出力 + 古いログの自動クリーンアップ."""

from __future__ import annotations

import logging
import platform
import sys
from datetime import date, timedelta
from pathlib import Path


def setup_logger(log_dir: Path, target_date: date | None = None) -> logging.Logger:
    """アプリケーションロガーを設定して返す."""
    log_dir.mkdir(parents=True, exist_ok=True)

    d = target_date or date.today()
    log_file = log_dir / f"{d.isoformat()}.log"

    logger = logging.getLogger("daily_sales")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ファイルハンドラ — DEBUG 以上をすべて記録
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # コンソールハンドラ — INFO 以上のみ表示
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 実行環境情報をログ先頭に記録
    logger.debug("=" * 60)
    logger.debug("実行環境情報")
    logger.debug("  Python: %s", sys.version)
    logger.debug("  Platform: %s", platform.platform())
    logger.debug("  対象日: %s", d.isoformat())
    logger.debug("  ログファイル: %s", log_file)
    try:
        import playwright
        logger.debug("  Playwright: %s", playwright.__version__)
    except Exception:
        pass
    logger.debug("=" * 60)

    # 古いログのクリーンアップ（30日以上前）
    _cleanup_old_logs(log_dir, keep_days=30)

    return logger


def _cleanup_old_logs(log_dir: Path, keep_days: int = 30) -> None:
    """指定日数より古いログファイルとスクリーンショットを削除する."""
    cutoff = date.today() - timedelta(days=keep_days)
    logger = logging.getLogger("daily_sales")

    for log_file in log_dir.glob("*.log"):
        try:
            file_date = date.fromisoformat(log_file.stem)
            if file_date < cutoff:
                log_file.unlink()
                logger.debug("古いログ削除: %s", log_file.name)
        except ValueError:
            pass  # 日付形式でないファイルは無視

    ss_dir = log_dir / "screenshots"
    if ss_dir.exists():
        for ss_file in ss_dir.glob("*.png"):
            try:
                # ファイル名: YYYY-MM-DD_site_xxx.png
                file_date = date.fromisoformat(ss_file.stem.split("_")[0])
                if file_date < cutoff:
                    ss_file.unlink()
                    logger.debug("古いスクリーンショット削除: %s", ss_file.name)
            except ValueError:
                pass
