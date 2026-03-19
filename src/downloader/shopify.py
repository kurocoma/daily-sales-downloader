"""Shopify Downloader — 注文データエクスポート + Fulfilled at フィルタ."""

from __future__ import annotations

import csv
import logging
from datetime import date
from io import StringIO
from pathlib import Path

from src.downloader.base import BaseDownloader
from src.utils.path_resolver import DownloadTarget, resolve_download_path

logger = logging.getLogger("daily_sales")

LOGIN_URL = "https://accounts.shopify.com/lookup"
ORDERS_URL = "https://admin.shopify.com/store/kurima-okinawa/orders"

# Fulfilled at 列のインデックス（0-based で 5 = 6列目）
FULFILLED_AT_COL = 5


class ShopifyDownloader(BaseDownloader):
    """Shopify から注文データをエクスポートし、Fulfilled at でフィルタして保存する."""

    site_name = "shopify"

    async def login(self) -> None:
        """Shopify にログイン（メール → パスワード 2段階）."""
        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # 既にログイン済み（admin ページにいる）ならスキップ
        if "admin.shopify.com" in self.page.url:
            logger.info("%s: ログイン済み（Cookie 復元）— スキップ", self.site_name)
            return

        # Step 1: メールアドレス入力
        cred = self.credentials["shopify"]
        email_input = self.page.locator("#account_email")
        await email_input.wait_for(state="visible", timeout=10000)
        await email_input.fill(cred.login_id)
        logger.info("%s: メールアドレス入力完了", self.site_name)

        # 「メールアドレスで続行」ボタンをクリック
        await self.page.locator('button.login-button[type="submit"]').click()
        logger.info("%s: メールアドレスで続行", self.site_name)
        await self.page.wait_for_timeout(3000)

        # Step 2: パスワード入力
        pw_input = self.page.locator("#account_password")
        await pw_input.wait_for(state="visible", timeout=10000)
        await pw_input.fill(cred.password)
        logger.info("%s: パスワード入力完了", self.site_name)

        # 「ログイン」ボタンをクリック
        await self.page.locator(
            'div.footer-form-submit button[type="submit"]'
        ).click()
        logger.info("%s: ログインボタンクリック", self.site_name)
        await self.page.wait_for_timeout(5000)

        # セキュリティ確認ページが出た場合 → 「次回通知する」
        try:
            remind_later = self.page.locator("a.remind-me-later-link")
            await remind_later.wait_for(state="visible", timeout=3000)
            await remind_later.click()
            logger.info("%s: セキュリティ確認 — 次回通知するをクリック", self.site_name)
            await self.page.wait_for_timeout(3000)
        except Exception:
            pass  # セキュリティ確認が出なければスキップ

        # admin 画面に到達するまで待機（最大30秒）
        for _ in range(6):
            if "admin.shopify.com" in self.page.url:
                break
            # アカウント選択画面が表示される場合 → アカウントをクリック
            if "/select" in self.page.url:
                await self._select_account()
            await self.page.wait_for_timeout(5000)
        else:
            # アカウント設定ページ等に遷移した場合 → admin に直接移動
            logger.info(
                "%s: admin 未到達（%s）→ 注文管理ページへ直接遷移",
                self.site_name, self.page.url,
            )
            await self.page.goto(ORDERS_URL, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(5000)
            # アカウント選択画面にリダイレクトされた場合
            if "/select" in self.page.url:
                await self._select_account()
                await self.page.wait_for_timeout(5000)
            if "admin.shopify.com" not in self.page.url:
                raise RuntimeError(
                    f"Shopify: admin 画面に到達できませんでした。現在の URL: {self.page.url}"
                )

        logger.info("%s: ログイン成功", self.site_name)

    async def _select_account(self) -> None:
        """アカウント選択画面で最初のアカウントをクリックする."""
        try:
            account_btn = self.page.locator(
                'button:has-text("株式会社くりま"), '
                'a:has-text("株式会社くりま"), '
                'div[role="button"]:has-text("株式会社くりま")'
            ).first
            if await account_btn.is_visible():
                await account_btn.click()
                logger.info("%s: アカウント選択 — 株式会社くりま", self.site_name)
                await self.page.wait_for_timeout(3000)
        except Exception:
            pass

    async def download(self) -> list[Path]:
        """注文データをエクスポートし、Fulfilled at でフィルタして保存."""
        target_date = self.config.target_date

        # 注文管理ページへ移動
        await self.page.goto(ORDERS_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)

        # 「エクスポート」ボタンをクリック（ActionMenu 内のボタンを指定）
        export_btn = self.page.locator(
            'div.Polaris-ActionMenu-SecondaryAction button:has(span:text("エクスポート"))'
        ).first
        await export_btn.wait_for(state="visible", timeout=15000)
        await export_btn.click()
        logger.info("%s: エクスポートボタンクリック", self.site_name)
        await self.page.wait_for_timeout(3000)

        # エクスポートモーダルで「注文をエクスポートする」ボタンをクリック
        export_confirm = self.page.locator(
            'button:has(span:text("注文をエクスポートする"))'
        )
        await export_confirm.wait_for(state="visible", timeout=10000)

        # CSV ダウンロード実行
        tmp_path = await self.wait_and_download_file(
            lambda: export_confirm.click(),
            timeout=120000,
        )
        logger.info("%s: CSV エクスポート完了", self.site_name)

        # CSV をフィルタして保存
        return await self._filter_and_save(tmp_path, target_date)

    async def _filter_and_save(
        self, tmp_path: Path, target_date: date
    ) -> list[Path]:
        """ダウンロードした CSV を Fulfilled at でフィルタして保存する.

        6列目（0-based index 5）の Fulfilled at が target_date と一致する行のみ残す。
        該当データがなければ空リストを返す。
        """
        raw_text = tmp_path.read_text(encoding="utf-8-sig")
        tmp_path.unlink(missing_ok=True)  # 一時ファイルを削除
        reader = csv.reader(StringIO(raw_text))

        header = next(reader)
        rows = list(reader)

        # target_date に一致する行を抽出
        date_str = target_date.isoformat()  # "2026-03-19"
        filtered_rows = []
        for row in rows:
            if len(row) <= FULFILLED_AT_COL:
                continue
            fulfilled_at = row[FULFILLED_AT_COL].strip()
            if not fulfilled_at:
                continue
            # Fulfilled at の日付部分を抽出して比較
            fulfilled_date = _parse_date(fulfilled_at)
            if fulfilled_date and fulfilled_date.isoformat() == date_str:
                filtered_rows.append(row)

        if not filtered_rows:
            logger.info(
                "%s: Fulfilled at = %s のデータなし — スキップ",
                self.site_name, date_str,
            )
            return []

        logger.info(
            "%s: %d 件のデータを抽出（Fulfilled at = %s）",
            self.site_name, len(filtered_rows), date_str,
        )

        # 保存先パスは Fulfilled at の日付で決定
        dest = resolve_download_path(
            self.config.download_base, DownloadTarget.SHOPIFY, target_date,
        )
        dest.parent.mkdir(parents=True, exist_ok=True)

        # フィルタ済み CSV を書き出し
        with open(dest, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(filtered_rows)

        logger.info("%s: 保存完了 → %s", self.site_name, dest)
        return [dest]


def _parse_date(value: str) -> date | None:
    """Fulfilled at の値から date を抽出する.

    Shopify のエクスポート CSV では日時形式が複数ありうる:
    - "2026-03-19 14:30:00 +0900"
    - "2026-03-19T14:30:00+09:00"
    - "2026-03-19"
    """
    if not value or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
