"""CLI エントリポイント — 日別売上集計データ自動ダウンロード."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# .env を読み込み（プロジェクトルートから）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.config import AppConfig, parse_args
from src.credential import load_credentials
from src.downloader.base import DownloadResult
from src.excel_refresh import refresh_and_filter, get_excel_path
from src.utils.logger import setup_logger

logger = logging.getLogger("daily_sales")

# サイト名 → Downloader クラスのマッピング（フェーズ2で各クラスを追加）
_DOWNLOADER_MAP: dict[str, type] = {}


def _register_downloaders() -> None:
    """利用可能な Downloader クラスを登録する."""
    from src.downloader.rakuten import RakutenDownloader
    from src.downloader.yahoo import YahooDownloader
    from src.downloader.amazon import AmazonDownloader
    from src.downloader.shopify import ShopifyDownloader
    from src.downloader.next_engine import NextEngineDownloader

    _DOWNLOADER_MAP["rakuten"] = RakutenDownloader
    _DOWNLOADER_MAP["yahoo"] = YahooDownloader
    _DOWNLOADER_MAP["amazon"] = AmazonDownloader
    _DOWNLOADER_MAP["shopify"] = ShopifyDownloader
    _DOWNLOADER_MAP["next_engine"] = NextEngineDownloader


async def async_main(config: AppConfig) -> dict[str, dict[str, DownloadResult]]:
    """全サイト × 全日付のダウンロードを実行する.

    処理順: サイトループ(外側) → 日付ループ(内側)
    → ログインは各サイト1回のみ、同一セッションで日付を切り替えて DL
    """
    credentials = load_credentials(config.credential_path)
    logger.info("認証情報を読み込みました: %s", list(credentials.keys()))
    logger.info(
        "対象日: %s / 対象サイト: %s",
        ", ".join(d.isoformat() for d in config.target_dates),
        config.target_sites,
    )

    # {date_iso: {site: DownloadResult}}
    all_results: dict[str, dict[str, DownloadResult]] = {
        d.isoformat(): {} for d in config.target_dates
    }

    stealth = Stealth()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.headless)

        for site in config.target_sites:
            logger.info("=" * 50)
            logger.info("%s: 処理開始（%d日分）", site, len(config.target_dates))
            logger.info("=" * 50)

            downloader_cls = _DOWNLOADER_MAP.get(site)
            if downloader_cls is None:
                logger.warning("%s: Downloader 未実装（スキップ）", site)
                for d in config.target_dates:
                    all_results[d.isoformat()][site] = DownloadResult(
                        site=site, success=False, error="未実装",
                    )
                continue

            # コンテキスト作成
            # Amazon / Shopify: persistent_context
            if site in ("amazon", "shopify"):
                user_data_dir = config.cookie_dir / f"{site}_profile"
                user_data_dir.mkdir(parents=True, exist_ok=True)
                # Shopify: Cloudflare Turnstile がヘッドレスを検出するため常に非ヘッドレス
                site_headless = False if site == "shopify" else config.headless
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=site_headless,
                    accept_downloads=True,
                    locale="ja-JP",
                    args=["--disable-blink-features=AutomationControlled"],
                )
            else:
                cookie_file = config.cookie_dir / f"{site}.json"
                storage_state = str(cookie_file) if cookie_file.exists() else None
                context = await browser.new_context(
                    storage_state=storage_state,
                    accept_downloads=True,
                    locale="ja-JP",
                )

            # Stealth 適用（自動化検出を回避）
            await stealth.apply_stealth_async(context)

            # ログイン1回 → 全日付 DL（レンジモードは1回で全期間カバー）
            downloader = downloader_cls(config, credentials, context)
            if config.range_days > 0 and site == "next_engine":
                # レンジモード: download() 内で range 処理するため run() を1回呼ぶ
                result = await downloader.run()
                # run() は単一 DownloadResult を返す → date_key は today
                from datetime import date as date_cls
                date_key = date_cls.today().isoformat()
                site_results = {date_key: result}
                # all_results に date_key が無い場合は追加
                if date_key not in all_results:
                    all_results[date_key] = {}
            else:
                site_results = await downloader.run_multi_dates(config.target_dates)

            # 結果を date → site 構造にマッピング
            for date_key, result in site_results.items():
                all_results[date_key][site] = result

            # Cookie 保存（1件でも成功していれば）
            any_ok = any(r.success for r in site_results.values())
            if any_ok and site not in ("amazon", "shopify"):
                config.cookie_dir.mkdir(parents=True, exist_ok=True)
                await context.storage_state(path=str(cookie_file))
                logger.info("%s: Cookie 保存完了", site)

            await context.close()

        await browser.close()

    return all_results


def report(
    all_results: dict[str, dict[str, DownloadResult]],
    total_elapsed: float = 0,
) -> None:
    """実行結果をログに出力する."""
    logger.info("=" * 50)
    logger.info("実行結果サマリー (合計 %.1f秒)", total_elapsed)
    logger.info("=" * 50)
    ok_count = 0
    ng_count = 0
    for date_str, results in all_results.items():
        logger.info("--- %s ---", date_str)
        for site, result in results.items():
            if result.success:
                ok_count += 1
                files_str = ", ".join(str(f) for f in result.files)
                logger.info("  [OK] %s: %s", site, files_str or "ファイルなし")
            else:
                ng_count += 1
                logger.error("  [NG] %s: %s", site, result.error)
    logger.info("結果: %d 成功 / %d 失敗 / %d 合計", ok_count, ng_count, ok_count + ng_count)


def cli(argv: list[str] | None = None) -> None:
    """CLI エントリポイント."""
    config = parse_args(argv)
    setup_logger(config.log_dir, config.target_dates[0])
    _register_downloaders()

    logger.info("日別売上集計データダウンロード開始")
    logger.info(
        "対象日数: %d (%s)",
        len(config.target_dates),
        ", ".join(d.isoformat() for d in config.target_dates),
    )
    start_time = time.monotonic()
    all_results = asyncio.run(async_main(config))
    total_elapsed = time.monotonic() - start_time
    report(all_results, total_elapsed)

    failed: list[str] = []
    for date_str, results in all_results.items():
        for site, r in results.items():
            if not r.success:
                failed.append(f"{date_str}/{site}")
    if failed:
        logger.error("失敗: %s", ", ".join(failed))
        sys.exit(1)

    logger.info("全サイト・全日付 正常完了")

    # レンジモードの場合は Excel/差異レポート更新をスキップ
    if config.range_days > 0:
        logger.info("レンジモードのため Excel/差異レポート更新をスキップ")
        return

    # Excel 集計ファイルのデータ更新 & 前日日付フィルタ
    target = config.target_dates[-1]
    excel_path = get_excel_path(target)
    try:
        logger.info("Excel 集計ファイル更新開始: %s", excel_path)
        refresh_and_filter(excel_path, target)
        logger.info("Excel 集計ファイル更新完了")
    except Exception:
        logger.exception("Excel 集計ファイル更新に失敗しました（DL自体は成功）")

    # 差異レポート生成（対象月分）
    try:
        _generate_reconciliation_report(target, config)
    except Exception:
        logger.exception("差異レポート生成に失敗しました（DL・Excel更新には影響なし）")


def _generate_reconciliation_report(target: date, config: AppConfig) -> None:
    """対象月の差異レポートを生成する."""
    from src.aggregator.reconcile import reconcile_all
    from src.aggregator.reconcile_excel import write_reconciliation_report

    year, month = target.year, target.month
    dl_base = config.download_base / str(year)
    master = config.download_base.parent / "商品管理シート.xlsm"
    tel = dl_base / "その他電話注文" / "その他電話注文.xlsm"
    output = config.log_dir / f"差異レポート_{year}年{month}月.xlsx"

    if not master.exists():
        logger.warning("商品管理シートが見つかりません: %s — 差異レポートをスキップ", master)
        return
    if not tel.exists():
        logger.warning("その他電話注文.xlsm が見つかりません: %s — 差異レポートをスキップ", tel)
        return

    logger.info("差異レポート生成開始: %d年%d月", year, month)
    results = reconcile_all(dl_base, master, tel, year, month)

    # サマリーをログ出力
    summary = results.get("サマリー")
    if summary is not None and not summary.empty:
        for site_name, grp in summary.groupby("サイト"):
            match_count = int(grp["一致件数"].sum())
            total_mm = int(grp["総合計不一致件数"].sum())
            product_mm = int(grp["商品計不一致件数"].sum())
            mall_only = int(grp["モール側のみ件数"].sum())
            logger.info(
                "差異レポート [%s]: 一致=%d, 総合計不一致=%d, 商品計不一致=%d, モール側のみ=%d",
                site_name, match_count, total_mm, product_mm, mall_only,
            )

    write_reconciliation_report(results, output, year, month)
    logger.info("差異レポート生成完了: %s", output)


if __name__ == "__main__":
    cli()
