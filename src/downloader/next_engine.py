"""ネクストエンジン Downloader."""

from __future__ import annotations

import logging
from pathlib import Path

from src.downloader.base import BaseDownloader
from src.utils.path_resolver import DownloadTarget, resolve_download_path

logger = logging.getLogger("daily_sales")

LOGIN_URL = "https://base.next-engine.org/users/sign_in/"
ORDER_URL = "https://main.next-engine.com/Userjyuchu/index?search_condi=17"


class NextEngineDownloader(BaseDownloader):
    """ネクストエンジンから購入者データ・商品情報データをダウンロードする."""

    site_name = "next_engine"

    async def login(self) -> None:
        """ネクストエンジンにログイン（Cookie 復元時はスキップ）."""
        cred = self.credentials["next_engine"]

        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # Cookie 同意バナーが表示されている場合は閉じる
        await self._dismiss_cookie_banner()

        # Cookie 復元でログイン済みならログイン処理をスキップ
        login_form = self.page.locator("#user_login_code")
        if await login_form.is_visible():
            await login_form.fill(cred.login_id)
            await self.page.fill("#user_password", cred.password)
            await self.page.click('input[name="commit"][value="ログイン"]')
            logger.info("%s: ログイン送信", self.site_name)
            await self.page.wait_for_load_state("domcontentloaded")
            await self.page.wait_for_timeout(3000)

            # お知らせページが表示される場合 → 「すべて既読にする」
            await self._handle_news_page()
        else:
            logger.info("%s: ログイン済み（Cookie 復元）— スキップ", self.site_name)

        # モーダル backdrop が残っている場合は除去
        await self.page.evaluate(
            'document.querySelectorAll(".modal-backdrop").forEach(e => e.remove())'
        )
        await self.page.wait_for_timeout(1000)

        # 「メイン機能」アプリをクリックして main ドメインへ遷移
        main_app = self.page.get_by_role("link", name="メイン機能")
        await main_app.wait_for(state="visible", timeout=15000)
        await main_app.click()
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(5000)
        logger.info("%s: メイン機能へ遷移完了", self.site_name)

    async def _dismiss_cookie_banner(self) -> None:
        """Cookie 同意バナー（cm-ov オーバーレイ）を閉じる."""
        try:
            consent_btn = self.page.locator("#cm-acceptAll, button:has-text('同意します')")
            if await consent_btn.is_visible(timeout=3000):
                await consent_btn.click()
                await self.page.wait_for_timeout(1000)
                logger.info("%s: Cookie 同意バナーを閉じました", self.site_name)
            else:
                # バナーの overlay が残っている場合は JS で除去
                removed = await self.page.evaluate(
                    'document.querySelectorAll("#cm-ov, #cc--main").forEach(e => e.remove())'
                )
                logger.debug("%s: Cookie バナー要素を除去", self.site_name)
        except Exception:
            # バナーが表示されなかった場合は無視
            pass

    async def _set_page_size(self) -> None:
        """表示件数を1000件に設定する."""
        try:
            page_sel = self.page.locator("#page_sel")
            if await page_sel.is_visible(timeout=3000):
                current = await page_sel.input_value()
                if current != "1000":
                    await page_sel.select_option(value="1000")
                    await self.page.wait_for_timeout(3000)
                    logger.info("%s: 表示件数を1000件に変更", self.site_name)
        except Exception:
            logger.debug("%s: 表示件数セレクタが見つかりません", self.site_name)

    async def _handle_news_page(self) -> None:
        """不定期に表示されるお知らせページを処理する."""
        try:
            mark_read_btn = self.page.locator('button.markasread[data-newsonly="1"]')
            if await mark_read_btn.is_visible(timeout=5000):
                # ダイアログ（confirm ポップアップ）を自動承認
                self.page.on("dialog", lambda dialog: dialog.accept())
                await mark_read_btn.click()
                await self.page.wait_for_timeout(2000)
                logger.info("%s: お知らせを既読にしました", self.site_name)
        except Exception:
            # お知らせページが表示されなかった場合は無視
            pass

    async def download(self) -> list[Path]:
        """受注検索 → 購入者データ DL → 商品情報データ DL."""
        files: list[Path] = []

        # 購入者データ
        if self.config.date_mode == "order":
            buyer_target = DownloadTarget.NE_BUYER_ORDER_DATE
        else:
            buyer_target = DownloadTarget.NE_BUYER
        buyer_file = await self._search_and_download(buyer_target)
        if buyer_file is not None:
            files.append(buyer_file)

        # 商品情報データ（明細一覧経由）
        product_file = await self._search_and_download_product()
        if product_file is not None:
            files.append(product_file)

        return files

    async def _search_and_download(self, target: DownloadTarget) -> Path | None:
        """受注検索 → 条件設定 → 検索 → ダウンロード."""
        target_date = self.config.target_date
        date_str = target_date.strftime("%Y/%m/%d")

        # 受注一覧へ遷移
        await self.page.goto(ORDER_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)
        logger.info("%s: 受注一覧へ遷移完了", self.site_name)

        # 表示件数を最大（1000件）に設定
        await self._set_page_size()

        # 「詳細検索」クリック
        await self.page.click("#jyuchu_dlg_open")
        await self.page.wait_for_timeout(2000)
        logger.info("%s: 詳細検索ダイアログを開きました", self.site_name)

        # 「クリア」押下
        await self.page.click('input[onclick="searchJyuchu.clear()"]')
        await self.page.wait_for_timeout(1000)

        # 受注キャンセル区分 → 0: 有効な受注です。
        await self.page.select_option(
            'select[name="sea_jyuchu_search_field49"]', value="0"
        )

        # 日付フィールド — date_mode に応じて出荷確定日 or 受注日
        if self.config.date_mode == "order":
            field_from = "#sea_jyuchu_search_field03_from"
            field_to = "#sea_jyuchu_search_field03_to"
        else:
            field_from = "#sea_jyuchu_search_field36_from"
            field_to = "#sea_jyuchu_search_field36_to"

        await self.page.fill(field_from, date_str)
        await self.page.fill(field_to, date_str)

        # 検索ボタン押下（ダイアログ内）
        await self.page.click("#ne_dlg_btn3_searchJyuchuDlg")
        logger.info("%s: 検索実行", self.site_name)

        # ダイアログ / backdrop 除去を待機
        await self.page.wait_for_timeout(5000)
        await self.page.evaluate('document.querySelectorAll(".modal-backdrop").forEach(e => e.remove())')

        # データ0件チェック
        no_data = self.page.locator('text=結果はありませんでした')
        if await no_data.is_visible():
            logger.info("%s: データ0件 — スキップ", self.site_name)
            return None

        # テーブルが表示されるまで待機
        await self.page.wait_for_selector(
            "#searchJyuchu_table_dl_lnk", timeout=60000
        )
        await self.page.wait_for_timeout(2000)

        # ダウンロード
        tmp_path = await self.wait_and_download_file(
            lambda: self.page.click("#searchJyuchu_table_dl_lnk"),
            timeout=60000,
        )

        dest = resolve_download_path(
            self.config.download_base, target, target_date
        )
        return await self.save_downloaded_file(tmp_path, dest)

    async def _search_and_download_product(self) -> Path | None:
        """明細一覧経由で商品情報データをダウンロードする."""
        target_date = self.config.target_date
        date_str = target_date.strftime("%Y/%m/%d")

        # 受注一覧へ再度遷移
        await self.page.goto(ORDER_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # 表示件数を最大（1000件）に設定
        await self._set_page_size()

        # 詳細検索 → 同じ条件で検索
        await self.page.click("#jyuchu_dlg_open")
        await self.page.wait_for_timeout(2000)
        await self.page.click('input[onclick="searchJyuchu.clear()"]')
        await self.page.wait_for_timeout(1000)
        await self.page.select_option(
            'select[name="sea_jyuchu_search_field49"]', value="0"
        )
        # 日付フィールド — date_mode に応じて出荷確定日 or 受注日
        if self.config.date_mode == "order":
            field_from = "#sea_jyuchu_search_field03_from"
            field_to = "#sea_jyuchu_search_field03_to"
        else:
            field_from = "#sea_jyuchu_search_field36_from"
            field_to = "#sea_jyuchu_search_field36_to"

        await self.page.fill(field_from, date_str)
        await self.page.fill(field_to, date_str)

        await self.page.click("#ne_dlg_btn3_searchJyuchuDlg")

        # ダイアログ / backdrop 除去を待機
        await self.page.wait_for_timeout(5000)
        await self.page.evaluate('document.querySelectorAll(".modal-backdrop").forEach(e => e.remove())')

        # データ0件チェック
        no_data = self.page.locator('text=結果はありませんでした')
        if await no_data.is_visible():
            logger.info("%s: データ0件（商品情報） — スキップ", self.site_name)
            return None

        # テーブル待機
        await self.page.wait_for_selector(
            "#searchJyuchu_table_dl_lnk", timeout=60000
        )
        await self.page.wait_for_timeout(2000)

        # 「全て選択」クリック
        await self.page.click("#all_check")
        await self.page.wait_for_timeout(1000)

        # 「明細一覧」クリック
        await self.page.click('img[alt="明細一覧"]')
        await self.page.wait_for_timeout(2000)

        # モーダル — 「伝票明細単位で出力」選択
        await self.page.click('span:has-text("伝票明細単位で出力")')
        await self.page.wait_for_timeout(500)

        # 「開く」ボタン押下 → 新タブが開く
        async with self.context.expect_page() as new_page_info:
            await self.page.click("#btn_meisai_exec")
        new_page = await new_page_info.value
        await new_page.wait_for_load_state("domcontentloaded")
        await new_page.wait_for_timeout(3000)

        # 新タブで「ダウンロード」クリック
        tmp_path: Path
        async with new_page.expect_download(timeout=60000) as dl_info:
            await new_page.click("#searchJyuchu_table_dl_lnk")
        download = await dl_info.value
        tmp_path = Path(await download.path())

        await new_page.close()

        if self.config.date_mode == "order":
            product_target = DownloadTarget.NE_PRODUCT_ORDER_DATE
        else:
            product_target = DownloadTarget.NE_PRODUCT
        dest = resolve_download_path(
            self.config.download_base, product_target, target_date
        )
        return await self.save_downloaded_file(tmp_path, dest)
