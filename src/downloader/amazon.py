"""Amazon Seller Central Downloader — 全注文レポート + 日別トランザクション."""

from __future__ import annotations

import logging
from pathlib import Path

from src.downloader.base import BaseDownloader
from src.utils.path_resolver import DownloadTarget, resolve_download_path

logger = logging.getLogger("daily_sales")

ALL_ORDER_URL = "https://sellercentral.amazon.co.jp/reportcentral/FlatFileAllOrdersReport/1"
TRANSACTION_URL = "https://sellercentral.amazon.co.jp/payments/event/view?resultsPerPage=10&pageNumber=1"


class AmazonDownloader(BaseDownloader):
    """Amazon Seller Central から全注文レポート + 日別トランザクションをダウンロードする."""

    site_name = "amazon"

    async def login(self) -> None:
        """Amazon にログイン（Cookie 復元で自動ログイン想定）.

        2FA があるため、初回は --no-headless で手動ログインし Cookie を保存する。
        Cookie が有効であればログイン画面をスキップできる。
        Cookie が失効している場合はエラーとなり、手動対応が必要。
        """
        # Cookie 復元済みの状態で Seller Central にアクセス
        await self.page.goto(ALL_ORDER_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # ログインページにリダイレクトされたかチェック
        current_url = self.page.url
        if "signin" in current_url.lower() or "ap/signin" in current_url.lower():
            if self.config.headless:
                raise RuntimeError(
                    "Amazon: Cookie が失効しています。"
                    "--no-headless で手動ログインして Cookie を保存してください。"
                    " 実行例: uv run python -m src.main --site amazon --no-headless"
                )
            # ID/PW を自動入力（2FA は手動）
            cred = self.credentials["amazon"]
            email_input = self.page.locator("#ap_email")
            if await email_input.is_visible():
                await email_input.fill(cred.login_id)
                # 「次に進む」クリック → パスワード画面へ
                await self.page.locator("input#continue").click()
                logger.info("%s: メールアドレス入力 → 次に進む", self.site_name)
                await self.page.wait_for_timeout(3000)
                # パスワード入力
                pw_input = self.page.locator("#ap_password")
                if await pw_input.is_visible():
                    await pw_input.fill(cred.password)
                    await self.page.locator("#signInSubmit").click()
                    logger.info("%s: パスワード入力 → 送信", self.site_name)

            # 2FA / アカウント選択を含むログイン完了を待機
            logger.info(
                "%s: 2FA が表示された場合はブラウザで手動操作してください。"
                "Seller Central に到達するまで待機します...",
                self.site_name,
            )
            for _ in range(120):  # 最大10分
                await self.page.wait_for_timeout(5000)
                url = self.page.url.lower()
                is_auth = any(k in url for k in ["signin", "ap/", "mfa", "auth"])
                if "sellercentral" in url and not is_auth:
                    break
            else:
                raise RuntimeError("Amazon: ログインがタイムアウトしました（10分）")

        # アカウント選択画面が表示される場合 → 「アカウントを選択」クリック
        await self.page.wait_for_timeout(3000)
        try:
            select_btn = self.page.locator('button:has-text("アカウントを選択"), input[value*="アカウントを選択"]')
            if await select_btn.is_visible():
                await select_btn.click()
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(3000)
                logger.info("%s: アカウント選択完了", self.site_name)
        except Exception:
            pass

        logger.info("%s: ログイン成功", self.site_name)

    async def download(self) -> list[Path]:
        """全注文レポート + 日別トランザクションをダウンロード."""
        files: list[Path] = []

        # --- 全注文レポート ---
        all_order_file = await self._download_all_order_report()
        files.append(all_order_file)

        # --- 日別トランザクション ---
        transaction_file = await self._download_transaction()
        if transaction_file is not None:
            files.append(transaction_file)

        return files

    async def _download_all_order_report(self) -> Path:
        """全注文レポートをダウンロードする."""
        target_date = self.config.target_date

        await self.page.goto(ALL_ORDER_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)

        # ツアーオーバーレイが表示される場合は除去
        await self.page.evaluate(
            'document.querySelectorAll("#react-joyride-portal, .react-joyride__overlay").forEach(e => e.remove())'
        )

        # レポート期間: 「過去7日間」を選択 — kat-dropdown を JS で操作
        await self.page.evaluate("""
            () => {
                const dropdown = document.querySelector('kat-dropdown.daily-time-picker-kat-dropdown-normal');
                if (dropdown) {
                    dropdown.value = '7';
                    dropdown.dispatchEvent(new CustomEvent('change', { bubbles: true, composed: true }));
                }
            }
        """)
        await self.page.wait_for_timeout(1000)
        # UI 上の選択を反映させるためクリック操作も試行
        dropdown = self.page.locator("kat-dropdown.daily-time-picker-kat-dropdown-normal")
        try:
            await dropdown.click(timeout=5000)
            await self.page.wait_for_timeout(500)
            opt = self.page.locator('kat-option[value="7"]')
            if await opt.is_visible():
                await opt.click()
                await self.page.wait_for_timeout(1000)
        except Exception:
            pass  # JS での value 設定が効いていれば OK
        logger.info("%s: レポート期間「過去7日間」を選択", self.site_name)

        # 「ダウンロードのリクエスト」クリック
        await self.page.click('kat-button[label="ダウンロードのリクエスト"]')
        logger.info("%s: 全注文レポート — ダウンロードリクエスト送信", self.site_name)
        await self.page.wait_for_timeout(3000)

        # テーブル1行目が「処理中」→「ダウンロード」に変わるまでポーリング (最大5分)
        for poll in range(30):  # 最大30回 × 10秒 = 5分
            # 1行目に「処理中」テキストがあるか確認
            processing = self.page.locator('text=処理中').first
            if not await processing.is_visible():
                # 処理中が消えた → ダウンロードボタンが出ているはず
                break
            logger.info(
                "%s: 全注文レポート — 処理中... (%d秒経過)",
                self.site_name, (poll + 1) * 10,
            )
            await self.page.wait_for_timeout(10000)
            # ページをリロードして最新状態を取得
            await self.page.reload(wait_until="domcontentloaded")
            await self.page.wait_for_timeout(3000)
            # リロード後にオーバーレイ除去
            await self.page.evaluate(
                'document.querySelectorAll("#react-joyride-portal, .react-joyride__overlay").forEach(e => e.remove())'
            )
        else:
            raise RuntimeError("全注文レポートの処理が5分以内に完了しませんでした")

        # 1行目のダウンロードボタンをクリック
        download_btn = self.page.locator(
            'kat-button[label="ダウンロード"][variant="secondary"][size="small"]'
        ).first
        await download_btn.wait_for(state="visible", timeout=10000)
        logger.info("%s: 全注文レポート — 処理完了", self.site_name)

        # ダウンロード実行
        tmp_path = await self.wait_and_download_file(
            lambda: download_btn.click(),
            timeout=60000,
        )

        dest = resolve_download_path(
            self.config.download_base, DownloadTarget.AMAZON_ALL_ORDER, target_date
        )
        return await self.save_downloaded_file(tmp_path, dest)

    async def _download_transaction(self) -> Path | None:
        """日別トランザクションをダウンロードする."""
        target_date = self.config.target_date
        date_str = target_date.strftime("%Y/%m/%d")

        await self.page.goto(TRANSACTION_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)

        # ツアーオーバーレイが表示される場合は繰り返し除去
        for _ in range(5):
            removed = await self.page.evaluate("""
                () => {
                    const els = document.querySelectorAll(
                        '#react-joyride-portal, .react-joyride__overlay, [class*="joyride"]'
                    );
                    els.forEach(e => e.remove());
                    return els.length;
                }
            """)
            if removed == 0:
                break
            await self.page.wait_for_timeout(1000)

        # 開始日・終了日を個別に設定 — kat-date-picker の value + CustomEvent
        iso_str = target_date.strftime("%Y-%m-%d")
        for picker_name in ["startDate", "endDate"]:
            await self.page.evaluate(f"""
                () => {{
                    const picker = document.querySelector('kat-date-picker[name="{picker_name}"]');
                    if (!picker) return;
                    picker.value = "{date_str}";
                    picker.dispatchEvent(new CustomEvent('change', {{
                        bubbles: true,
                        composed: true,
                        detail: {{ isoValue: "{iso_str}", value: "{date_str}" }}
                    }}));
                }}
            """)
            await self.page.wait_for_timeout(1000)
            logger.info("%s: %s = %s セット完了", self.site_name, picker_name, date_str)

        # 「更新」ボタン押下（force で overlay 回避）
        await self.page.locator('kat-button[label="更新"]').click(force=True)
        logger.info("%s: 日別トランザクション — 更新リクエスト送信", self.site_name)
        await self.page.wait_for_timeout(5000)

        # データ0件チェック（「結果が見つかりませんでした」）
        no_data = self.page.locator('text=結果が見つかりませんでした')
        if await no_data.is_visible():
            logger.info("%s: トランザクションデータ0件 — スキップ", self.site_name)
            return None

        # 「ダウンロード」ボタン出現待機
        download_btn = self.page.locator('kat-button.download-button[label="ダウンロード"]')
        await download_btn.wait_for(state="visible", timeout=120000)

        # ダウンロード実行
        tmp_path = await self.wait_and_download_file(
            lambda: download_btn.click(),
            timeout=60000,
        )

        dest = resolve_download_path(
            self.config.download_base, DownloadTarget.AMAZON_TRANSACTION, target_date
        )
        return await self.save_downloaded_file(tmp_path, dest)
