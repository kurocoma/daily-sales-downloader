"""ネクストエンジン Downloader."""

from __future__ import annotations

import logging
from pathlib import Path

from src.downloader.base import BaseDownloader
from src.utils.path_resolver import (
    DownloadTarget,
    resolve_download_path,
    resolve_range_download_path,
)

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
        # レンジモードの場合は download_range() に委譲
        if self.config.range_days > 0:
            return await self.download_range()

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

    async def download_range(self) -> list[Path]:
        """日付レンジを7日チャンクに分割してDL→CSV結合.

        NE のダウンロード上限は表示件数(1000件)に制限されるため、
        7日ごとに分割して安全にダウンロードし、最後に1ファイルに結合する。
        """
        from datetime import timedelta
        import csv
        import io

        date_from = self.config.date_range_from
        date_to = self.config.date_range_to
        logger.info(
            "%s: レンジダウンロード %s ~ %s (%d日間, 7日チャンク)",
            self.site_name,
            date_from.strftime("%Y/%m/%d"),
            date_to.strftime("%Y/%m/%d"),
            self.config.range_days,
        )

        # 7日チャンクに分割
        chunks: list[tuple] = []
        chunk_start = date_from
        while chunk_start <= date_to:
            chunk_end = min(chunk_start + timedelta(days=6), date_to)
            chunks.append((chunk_start, chunk_end))
            chunk_start = chunk_end + timedelta(days=1)

        logger.info("%s: %d チャンクに分割", self.site_name, len(chunks))

        # 購入者データ: チャンクごとにDL→結合
        buyer_rows: list[str] = []
        buyer_header: str | None = None
        for i, (c_from, c_to) in enumerate(chunks):
            logger.info(
                "%s: [buyer %d/%d] %s ~ %s",
                self.site_name, i + 1, len(chunks),
                c_from.strftime("%Y/%m/%d"), c_to.strftime("%Y/%m/%d"),
            )
            tmp = await self._search_and_download_range(
                DownloadTarget.NE_BUYER_RANGE, c_from, c_to,
            )
            if tmp is not None:
                with open(tmp, "r", encoding="cp932") as f:
                    lines = f.readlines()
                if lines:
                    if buyer_header is None:
                        buyer_header = lines[0]
                    buyer_rows.extend(lines[1:])  # skip header
                # 一時ファイル削除
                tmp.unlink(missing_ok=True)

        # 商品情報データ: チャンクごとにDL→結合
        product_rows: list[str] = []
        product_header: str | None = None
        for i, (c_from, c_to) in enumerate(chunks):
            logger.info(
                "%s: [product %d/%d] %s ~ %s",
                self.site_name, i + 1, len(chunks),
                c_from.strftime("%Y/%m/%d"), c_to.strftime("%Y/%m/%d"),
            )
            tmp = await self._search_and_download_product_range(c_from, c_to)
            if tmp is not None:
                with open(tmp, "r", encoding="cp932") as f:
                    lines = f.readlines()
                if lines:
                    if product_header is None:
                        product_header = lines[0]
                    product_rows.extend(lines[1:])  # skip header
                tmp.unlink(missing_ok=True)

        # 結合ファイル書き出し
        files: list[Path] = []

        if buyer_header and buyer_rows:
            dest = resolve_range_download_path(
                self.config.download_base,
                DownloadTarget.NE_BUYER_RANGE,
                date_from,
                date_to,
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="cp932", newline="") as f:
                f.write(buyer_header)
                f.writelines(buyer_rows)
            logger.info("%s: 購入者データ結合 → %s (%d行)", self.site_name, dest, len(buyer_rows))
            files.append(dest)

        if product_header and product_rows:
            dest = resolve_range_download_path(
                self.config.download_base,
                DownloadTarget.NE_PRODUCT_RANGE,
                date_from,
                date_to,
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="cp932", newline="") as f:
                f.write(product_header)
                f.writelines(product_rows)
            logger.info("%s: 商品情報データ結合 → %s (%d行)", self.site_name, dest, len(product_rows))
            files.append(dest)

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

    # ── レンジダウンロード用メソッド ──

    async def _search_and_download_range(
        self,
        target: DownloadTarget,
        date_from,
        date_to,
    ) -> Path | None:
        """受注検索（日付レンジ）→ 条件設定 → 検索 → ダウンロード."""
        date_from_str = date_from.strftime("%Y/%m/%d")
        date_to_str = date_to.strftime("%Y/%m/%d")

        # 受注一覧へ遷移
        await self.page.goto(ORDER_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(5000)
        logger.info("%s: 受注一覧へ遷移完了（レンジ）", self.site_name)

        # 表示件数を最大（1000件）に設定
        await self._set_page_size()

        # 「詳細検索」クリック
        await self.page.click("#jyuchu_dlg_open")
        await self.page.wait_for_timeout(2000)
        logger.info("%s: 詳細検索ダイアログを開きました（レンジ）", self.site_name)

        # 「クリア」押下
        await self.page.click('input[onclick="searchJyuchu.clear()"]')
        await self.page.wait_for_timeout(1000)

        # 受注キャンセル区分 → 0: 有効な受注です。
        await self.page.select_option(
            'select[name="sea_jyuchu_search_field49"]', value="0"
        )

        # 日付フィールド — レンジモードは常に受注日（field03）
        field_from = "#sea_jyuchu_search_field03_from"
        field_to = "#sea_jyuchu_search_field03_to"

        await self.page.fill(field_from, date_from_str)
        await self.page.fill(field_to, date_to_str)

        # 検索ボタン押下（ダイアログ内）
        await self.page.click("#ne_dlg_btn3_searchJyuchuDlg")
        logger.info("%s: 検索実行（レンジ %s ~ %s）", self.site_name, date_from_str, date_to_str)

        # ダイアログ / backdrop 除去を待機
        await self.page.wait_for_timeout(5000)
        await self.page.evaluate('document.querySelectorAll(".modal-backdrop").forEach(e => e.remove())')

        # データ0件チェック
        no_data = self.page.locator('text=結果はありませんでした')
        if await no_data.is_visible():
            logger.info("%s: データ0件（レンジ） — スキップ", self.site_name)
            return None

        # テーブルが表示されるまで待機
        await self.page.wait_for_selector(
            "#searchJyuchu_table_dl_lnk", timeout=60000
        )
        await self.page.wait_for_timeout(2000)

        # ダウンロード → 一時パスをそのまま返す（結合はdownload_range()が行う）
        tmp_path = await self.wait_and_download_file(
            lambda: self.page.click("#searchJyuchu_table_dl_lnk"),
            timeout=120000,
        )
        return tmp_path

    async def _search_and_download_product_range(
        self,
        date_from,
        date_to,
    ) -> Path | None:
        """明細一覧経由で商品情報データをレンジダウンロードする."""
        date_from_str = date_from.strftime("%Y/%m/%d")
        date_to_str = date_to.strftime("%Y/%m/%d")

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

        # 日付フィールド — レンジモードは常に受注日（field03）
        field_from = "#sea_jyuchu_search_field03_from"
        field_to = "#sea_jyuchu_search_field03_to"

        await self.page.fill(field_from, date_from_str)
        await self.page.fill(field_to, date_to_str)

        await self.page.click("#ne_dlg_btn3_searchJyuchuDlg")

        # ダイアログ / backdrop 除去を待機
        await self.page.wait_for_timeout(5000)
        await self.page.evaluate('document.querySelectorAll(".modal-backdrop").forEach(e => e.remove())')

        # データ0件チェック
        no_data = self.page.locator('text=結果はありませんでした')
        if await no_data.is_visible():
            logger.info("%s: データ0件（商品情報レンジ） — スキップ", self.site_name)
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
        async with new_page.expect_download(timeout=120000) as dl_info:
            await new_page.click("#searchJyuchu_table_dl_lnk")
        download = await dl_info.value
        tmp_path = Path(await download.path())

        await new_page.close()

        # 一時パスをそのまま返す（結合はdownload_range()が行う）
        return tmp_path
