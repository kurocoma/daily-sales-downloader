"""Amazon セッション定期リフレッシュ — Cookie の有効期限を延長する.

Windows Task Scheduler で30分〜1時間ごとに実行することで、
Amazon Seller Central のセッションを維持する。

使用例:
    uv run python -m src.session_refresh
    uv run python -m src.session_refresh --interval 30  # 30分間隔で継続実行
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from src.config import COOKIE_DIR

logger = logging.getLogger("session_refresh")

AMAZON_DASHBOARD_URL = "https://sellercentral.amazon.co.jp/home"


def _setup_logger() -> None:
    """簡易ロガーを設定する."""
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)


async def refresh_amazon_session() -> bool:
    """Amazon Seller Central にアクセスしてセッションをリフレッシュする.

    Returns:
        True: セッション有効（リフレッシュ成功）
        False: セッション切れ（再ログインが必要）
    """
    stealth = Stealth()
    user_data_dir = COOKIE_DIR / "amazon_profile"

    if not user_data_dir.exists():
        logger.error("Amazon プロファイルが見つかりません: %s", user_data_dir)
        logger.error("先に --no-headless で手動ログインしてください")
        return False

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
            locale="ja-JP",
            args=["--disable-blink-features=AutomationControlled"],
        )
        await stealth.apply_stealth_async(context)

        page = await context.new_page()
        try:
            await page.goto(AMAZON_DASHBOARD_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            current_url = page.url.lower()
            if "signin" in current_url or "ap/signin" in current_url:
                logger.warning(
                    "Amazon セッション切れ — 再ログインが必要です。"
                    "実行: uv run python -m src.main --site amazon --no-headless"
                )
                return False

            title = await page.title()
            logger.info("Amazon セッションリフレッシュ成功 — %s", title)
            return True
        except Exception as e:
            logger.error("Amazon セッションリフレッシュ失敗: %s", e)
            return False
        finally:
            await page.close()
            await context.close()


async def run_periodic(interval_minutes: int) -> None:
    """指定間隔で定期的にリフレッシュを実行する."""
    logger.info("定期リフレッシュ開始（%d分間隔）", interval_minutes)
    while True:
        success = await refresh_amazon_session()
        if not success:
            logger.error("セッション切れを検知。手動対応が必要です。")
        next_run = interval_minutes * 60
        logger.info("次回リフレッシュ: %d分後", interval_minutes)
        await asyncio.sleep(next_run)


def main() -> None:
    """CLI エントリポイント."""
    parser = argparse.ArgumentParser(
        description="Amazon Seller Central セッションリフレッシュ",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="定期実行の間隔（分）。0 の場合は1回だけ実行して終了（デフォルト: 0）",
    )
    args = parser.parse_args()

    _setup_logger()

    if args.interval > 0:
        asyncio.run(run_periodic(args.interval))
    else:
        success = asyncio.run(refresh_amazon_session())
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
