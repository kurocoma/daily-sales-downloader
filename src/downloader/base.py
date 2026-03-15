"""基底ダウンローダー — 共通のログイン・DL・リトライ・スクリーンショット処理."""

from __future__ import annotations

import logging
import time
import traceback
from abc import ABC, abstractmethod
from copy import copy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from playwright.async_api import BrowserContext, Page

from src.config import AppConfig
from src.credential import SiteCredential

logger = logging.getLogger("daily_sales")


@dataclass
class DownloadResult:
    """ダウンロード結果."""

    site: str
    success: bool
    files: list[Path] = field(default_factory=list)
    error: str = ""


class BaseDownloader(ABC):
    """各モール Downloader の基底クラス."""

    site_name: str = "base"

    def __init__(
        self,
        config: AppConfig,
        credentials: dict[str, SiteCredential],
        context: BrowserContext,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.context = context
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Page not initialized. Call run() first.")
        return self._page

    async def run(self) -> DownloadResult:
        """メインフロー: ページ作成 → ログイン → ダウンロード → 保存."""
        self._page = await self.context.new_page()
        start_time = time.monotonic()
        try:
            logger.info("%s: ログイン開始", self.site_name)
            await self.login()
            logger.info("%s: ログイン成功", self.site_name)

            logger.info("%s: ダウンロード開始", self.site_name)
            files = await self.download()
            elapsed = time.monotonic() - start_time
            logger.info(
                "%s: ダウンロード完了 — %d ファイル (%.1f秒)",
                self.site_name, len(files), elapsed,
            )

            return DownloadResult(site=self.site_name, success=True, files=files)
        except Exception as e:
            elapsed = time.monotonic() - start_time
            await self._log_error(e, elapsed)
            return DownloadResult(site=self.site_name, success=False, error=str(e))
        finally:
            try:
                await self._page.close()
            except Exception:
                pass  # ブラウザ切断時は無視

    async def run_multi_dates(self, dates: list[date]) -> dict[str, DownloadResult]:
        """複数日付を1セッション（ログイン1回）で処理する.

        Returns:
            {日付ISO文字列: DownloadResult} の辞書
        """
        self._page = await self.context.new_page()
        results: dict[str, DownloadResult] = {}
        original_dates = self.config.target_dates

        try:
            logger.info("%s: ログイン開始", self.site_name)
            await self.login()
            logger.info("%s: ログイン成功", self.site_name)

            for target_date in dates:
                date_key = target_date.isoformat()
                self.config.target_dates = [target_date]
                start_time = time.monotonic()

                try:
                    logger.info(
                        "%s: [%s] ダウンロード開始", self.site_name, date_key,
                    )
                    files = await self.download()
                    elapsed = time.monotonic() - start_time
                    logger.info(
                        "%s: [%s] ダウンロード完了 — %d ファイル (%.1f秒)",
                        self.site_name, date_key, len(files), elapsed,
                    )
                    results[date_key] = DownloadResult(
                        site=self.site_name, success=True, files=files,
                    )
                except Exception as e:
                    elapsed = time.monotonic() - start_time
                    await self._log_error(e, elapsed, date_key)
                    results[date_key] = DownloadResult(
                        site=self.site_name, success=False, error=str(e),
                    )

        except Exception as e:
            # ログイン自体が失敗 → 全日付を失敗にする
            for target_date in dates:
                date_key = target_date.isoformat()
                if date_key not in results:
                    results[date_key] = DownloadResult(
                        site=self.site_name,
                        success=False,
                        error=f"ログイン失敗: {e}",
                    )
            await self._log_error(e, 0)
        finally:
            self.config.target_dates = original_dates
            try:
                await self._page.close()
            except Exception:
                pass

        return results

    @abstractmethod
    async def login(self) -> None:
        """サイトにログインする."""

    @abstractmethod
    async def download(self) -> list[Path]:
        """データをダウンロードし、保存先パスのリストを返す."""

    async def _log_error(
        self, e: Exception, elapsed: float, date_key: str = "",
    ) -> None:
        """エラーの詳細情報をログに記録し、スクリーンショットを保存する."""
        prefix = f"{self.site_name}: [{date_key}]" if date_key else f"{self.site_name}:"
        logger.error("%s エラー (%.1f秒経過) — %s", prefix, elapsed, e)
        logger.debug("%s スタックトレース:\n%s", prefix, traceback.format_exc())
        try:
            logger.debug("%s エラー時の URL: %s", prefix, self.page.url)
            title = await self.page.title()
            logger.debug("%s エラー時のページタイトル: %s", prefix, title)
        except Exception:
            pass
        await self._save_screenshot(date_key)

    async def _save_screenshot(self, date_key: str = "") -> None:
        """エラー時にスクリーンショットを保存する."""
        try:
            ss_dir = self.config.log_dir / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)
            d = date_key or self.config.target_date.isoformat()
            path = ss_dir / f"{d}_{self.site_name}_error.png"
            await self.page.screenshot(path=path, full_page=True)
            logger.info("%s: スクリーンショット保存 → %s", self.site_name, path)
        except Exception as e:
            logger.warning("%s: スクリーンショット保存失敗 — %s", self.site_name, e)

    async def wait_and_download_file(self, trigger_action, timeout: float = 60000) -> Path:
        """ダウンロードトリガーを実行し、DLされたファイルのパスを返す.

        Args:
            trigger_action: ダウンロードを開始する async callable
            timeout: ダウンロード待機タイムアウト (ms)

        Returns:
            ダウンロードされたファイルの一時パス
        """
        async with self.page.expect_download(timeout=timeout) as dl_info:
            await trigger_action()
        download = await dl_info.value
        tmp_path = Path(await download.path())
        return tmp_path

    async def save_downloaded_file(self, tmp_path: Path, dest_path: Path) -> Path:
        """ダウンロードした一時ファイルを最終保存先に移動する."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(tmp_path), str(dest_path))
        logger.info("%s: 保存完了 → %s", self.site_name, dest_path)
        return dest_path
