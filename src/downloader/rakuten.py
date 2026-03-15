"""楽天市場 Downloader."""

from __future__ import annotations

import logging
from pathlib import Path

from src.downloader.base import BaseDownloader
from src.utils.path_resolver import DownloadTarget, resolve_download_path

logger = logging.getLogger("daily_sales")

LOGIN_URL = "https://glogin.rms.rakuten.co.jp/?module=BizAuth&action=BizAuthCustomerAttest&sp_id=1"
CSV_DL_URL = "https://csvdl-rp.rms.rakuten.co.jp/rms/mall/csvdl/CD02_01_001?dataType=opp_order#result"


class RakutenDownloader(BaseDownloader):
    """楽天市場の日別売上データをダウンロードする."""

    site_name = "rakuten"

    async def login(self) -> None:
        """楽天 RMS にログイン（4画面）."""
        admin = self.credentials["rakuten_admin"]
        user = self.credentials["rakuten_user"]

        # --- 1画面目: R-Login ID + パスワード ---
        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self.page.wait_for_selector("#rlogin-username-ja", timeout=15000)
        await self.page.fill("#rlogin-username-ja", admin.login_id)
        await self.page.fill("#rlogin-password-ja", admin.password)
        async with self.page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            await self.page.click('button.rf-button-primary[name="submit"]')
        logger.info("%s: 1画面目 完了", self.site_name)

        # --- 2画面目: 楽天会員ログイン（ID入力 → 次へ） ---
        # Cookie 復元時はID記憶済みでパスワード画面に直接飛ぶことがある
        await self.page.wait_for_timeout(3000)

        # パスワード入力欄が既に表示されているか確認
        pw_input = self.page.locator('input[type="password"]').first
        if not await pw_input.is_visible():
            # ID入力画面 → ユーザID入力 → 次へ
            id_input = self.page.locator('input[type="text"], input[name="u"]').first
            await id_input.wait_for(state="visible", timeout=30000)
            await id_input.fill(user.login_id)
            next_btn_2a = self.page.locator('div[role="button"]:has-text("次へ"), button:has-text("次へ")').first
            await next_btn_2a.click()
            logger.info("%s: 2画面目a 完了（楽天会員ID入力）", self.site_name)
            await self.page.wait_for_timeout(3000)
            await pw_input.wait_for(state="visible", timeout=30000)
        else:
            logger.info("%s: 2画面目a スキップ（ID記憶済み）", self.site_name)

        # --- 2画面目b: パスワード入力 ---
        await pw_input.fill(user.password)
        # 「次へ」or「ログイン」ボタン — visible フィルタ + force click
        next_btn_2b = self.page.locator(
            'div[role="button"]:visible:has-text("次へ"), '
            'div[role="button"]:visible:has-text("ログイン")'
        ).first
        await next_btn_2b.click(force=True)
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(3000)
        logger.info("%s: 2画面目b 完了（パスワード入力）", self.site_name)

        # --- 3画面目: 「次へ」ボタン（存在する場合） ---
        try:
            await self.page.wait_for_selector(
                'button.rf-button-primary[name="submit"]', timeout=10000
            )
            async with self.page.expect_navigation(
                wait_until="domcontentloaded", timeout=30000
            ):
                await self.page.click('button.rf-button-primary[name="submit"]')
            logger.info("%s: 3画面目 完了", self.site_name)
        except Exception:
            logger.info("%s: 3画面目 スキップ（表示されず）", self.site_name)

        # --- 4画面目: RMS利用確認（存在する場合） ---
        try:
            await self.page.wait_for_selector(
                'button.btn-reset.btn-round.btn-red[type="submit"]', timeout=10000
            )
            async with self.page.expect_navigation(
                wait_until="domcontentloaded", timeout=30000
            ):
                await self.page.click(
                    'button.btn-reset.btn-round.btn-red[type="submit"]'
                )
            logger.info("%s: 4画面目 完了（RMS利用確認）", self.site_name)
        except Exception:
            logger.info("%s: 4画面目 スキップ（表示されず）", self.site_name)

        await self.page.wait_for_load_state("domcontentloaded")

    async def download(self) -> list[Path]:
        """CSV DL ページで条件設定 → データ作成 → ダウンロード."""
        target_date = self.config.target_date
        date_str = target_date.strftime("%Y-%m-%d")

        # CSV DL ページへ遷移（「認証が必要です」が出たら再ログイン、最大3回）
        for auth_retry in range(3):
            await self.page.goto(CSV_DL_URL, wait_until="domcontentloaded")
            await self.page.wait_for_timeout(3000)

            auth_required = self.page.locator('text=認証が必要です')
            if not await auth_required.is_visible():
                break
            logger.warning(
                "%s: 「認証が必要です」検出 (%d回目) → 再ログイン",
                self.site_name, auth_retry + 1,
            )
            await self.login()
        else:
            raise RuntimeError("楽天: 認証エラーが繰り返し発生しています")

        await self.page.wait_for_selector('select[name="fromYmd"]', timeout=30000)

        # 期間指定: 開始日・終了日を前日に設定
        await self.page.select_option('select[name="fromYmd"]', value=date_str)
        await self.page.select_option('select[name="toYmd"]', value=date_str)

        # 発送日ラジオボタン
        await self.page.click('input#r06[name="dateType"]')

        # 出力テンプレート → 全カラムダウンロード用 (value="-1")
        await self.page.select_option('select[name="templateId"]', value="-1")

        # 「データを作成する」クリック
        await self.page.click("#dataCreateBtn")
        logger.info("%s: データ作成リクエスト送信", self.site_name)

        # データ0件チェック（「入力内容に誤りがあります」+「データ件数は0件」）
        await self.page.wait_for_timeout(3000)
        no_data = self.page.locator('text=この条件でのデータ件数は0件です')
        if await no_data.is_visible():
            logger.info("%s: データ0件 — スキップ", self.site_name)
            return []

        # CSV ダウンロード用ユーザー名・パスワード入力を待機
        csv_cred = self.credentials["rakuten_csv"]
        await self.page.wait_for_selector('input#user[name="user"]', timeout=120000)
        logger.info("%s: CSV ダウンロード認証入力画面", self.site_name)

        await self.page.fill('input#user[name="user"]', csv_cred.login_id)
        await self.page.fill(
            'input[name="downloadPassword"], input[type="password"]',
            csv_cred.password,
        )

        # 「ダウンロードする」ボタンクリック → ファイル DL
        tmp_path = await self.wait_and_download_file(
            lambda: self.page.click("#downloadBtn"),
            timeout=60000,
        )

        # 保存先に移動
        dest = resolve_download_path(
            self.config.download_base, DownloadTarget.RAKUTEN, target_date
        )
        saved = await self.save_downloaded_file(tmp_path, dest)
        return [saved]
