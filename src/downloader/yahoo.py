"""Yahoo Shopping Downloader."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.downloader.base import BaseDownloader
from src.utils.path_resolver import DownloadTarget, resolve_download_path

logger = logging.getLogger("daily_sales")

_STORE_ID = os.environ.get("YAHOO_STORE_ID", "your_store_id")
LOGIN_URL = f"https://pro.store.yahoo.co.jp/pro.{_STORE_ID}"
ORDER_URL = f"https://pro.store.yahoo.co.jp/pro.{_STORE_ID}/order/manage/index"


class YahooDownloader(BaseDownloader):
    """Yahoo Shopping の注文データ・商品データをダウンロードする."""

    site_name = "yahoo"

    async def login(self) -> None:
        """Yahoo にログイン（Cookie 復元時はスキップ）."""
        cred = self.credentials["yahoo"]

        # ストアページへ → Yahoo ログイン画面にリダイレクト（or 既にログイン済み）
        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # Cookie 復元でログイン済みならスキップ
        login_input = self.page.locator('input[name="handle"]')
        if not await login_input.is_visible():
            logger.info("%s: ログイン済み（Cookie 復元）— スキップ", self.site_name)
            return

        # --- 1画面目: ID 入力 → 次へ ---
        await login_input.fill(cred.login_id)
        await self.page.click('button:has-text("次へ")')
        logger.info("%s: 1画面目 完了（ID入力）", self.site_name)

        # --- 2画面目: パスキー or パスワード ---
        await self.page.wait_for_timeout(3000)

        pw_input = self.page.locator('input[name="password"]')
        alt_login = self.page.locator(':has-text("他の方法でログイン")').last

        if not await pw_input.is_visible():
            await alt_login.click()
            logger.info("%s: パスキー画面 → 他の方法でログイン", self.site_name)
            await self.page.wait_for_timeout(3000)

            pw_btn = self.page.locator('button:has-text("パスワード")').first
            await pw_btn.wait_for(state="visible", timeout=10000)
            await pw_btn.click()
            logger.info("%s: パスワードログインを選択", self.site_name)
            await self.page.wait_for_timeout(3000)

        await self.page.wait_for_selector(
            'input[name="password"]', timeout=15000
        )
        await self.page.fill('input[name="password"]', cred.password)
        await self.page.click('button:has-text("ログイン")')
        logger.info("%s: 2画面目 完了（パスワード入力）", self.site_name)

        await self.page.wait_for_load_state("domcontentloaded")

    async def download(self) -> list[Path]:
        """注文管理画面 → 詳細検索 → 出荷日設定 → 2ファイル DL."""
        target_date = self.config.target_date
        date_str = target_date.strftime("%Y/%m/%d")

        # 注文管理画面へ
        await self.page.goto(ORDER_URL, wait_until="domcontentloaded")
        await self.page.wait_for_selector("#tab", timeout=15000)

        # 詳細検索タブへ切替
        await self.page.click('ul#tab a[href="#tab02"]')
        await self.page.wait_for_timeout(1000)
        logger.info("%s: 詳細検索タブ切替完了", self.site_name)

        # 出荷日の開始・終了に日付を入力
        await self.page.fill("#ShipDateFrom", date_str)
        await self.page.fill("#ShipDateTo", date_str)

        # 「注文データダウンロード」クリック（詳細検索タブ側の可視ボタン）
        dl_btn = self.page.locator(
            'a[onclick*="openSelectDownloadFilePage"]:visible'
        ).first
        await dl_btn.click()
        await self.page.wait_for_timeout(3000)
        logger.info("%s: 注文データダウンロード画面を開きました", self.site_name)

        # データ0件チェック（「該当する注文がありません」）
        no_data = self.page.locator('text=該当する注文がありません')
        if await no_data.is_visible():
            logger.info("%s: データ0件 — スキップ", self.site_name)
            return []

        downloaded_files: list[Path] = []

        # --- 注文データ DL ---
        # 出庫管理用_ver2（注文データ）行のリンクをクリック
        order_link = self.page.locator(
            'text=出庫管理用_ver2(注文データ)'
        ).locator("..").locator("..").locator('a[onclick*="fileDownload"]').first
        tmp_order = await self.wait_and_download_file(
            lambda: order_link.click(),
            timeout=60000,
        )
        dest_order = resolve_download_path(
            self.config.download_base, DownloadTarget.YAHOO_ORDER, target_date
        )
        saved_order = await self.save_downloaded_file(tmp_order, dest_order)
        downloaded_files.append(saved_order)

        # --- 商品データ DL ---
        item_link = self.page.locator(
            'text=出庫管理用_ver2(商品データ)'
        ).locator("..").locator("..").locator('a[onclick*="fileDownload"]').first
        tmp_item = await self.wait_and_download_file(
            lambda: item_link.click(),
            timeout=60000,
        )
        dest_item = resolve_download_path(
            self.config.download_base, DownloadTarget.YAHOO_ITEM, target_date
        )
        saved_item = await self.save_downloaded_file(tmp_item, dest_item)
        downloaded_files.append(saved_item)

        return downloaded_files
