"""設定管理 — CLI 引数パース・アプリケーション設定."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SITES = ("rakuten", "yahoo", "amazon", "shopify", "next_engine")

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIAL_PATH = BASE_DIR / "docs" / "ID・PW.xlsx"
COOKIE_DIR = BASE_DIR / "data" / "cookies"
LOG_DIR = BASE_DIR / "logs"

_DEFAULT_DL_BASE = r"C:\Users\{username}\日別売上集計"
DOWNLOAD_BASE_TEMPLATE = os.environ.get("DL_BASE_PATH", _DEFAULT_DL_BASE)


@dataclass
class AppConfig:
    """アプリケーション設定."""

    username: str
    target_dates: list[date]
    target_sites: list[str] = field(default_factory=lambda: list(SITES))
    max_retries: int = 3
    retry_delay: float = 5.0
    headless: bool = True
    date_mode: str = "shipment"
    range_days: int = 0
    credential_path: Path = CREDENTIAL_PATH
    cookie_dir: Path = COOKIE_DIR
    log_dir: Path = LOG_DIR

    @property
    def target_date(self) -> date:
        """後方互換: 単一日付が必要な場合は先頭を返す."""
        return self.target_dates[0]

    @property
    def download_base(self) -> Path:
        """ダウンロード保存先のベースパス."""
        return Path(DOWNLOAD_BASE_TEMPLATE.format(username=self.username))

    @property
    def date_range_from(self) -> date:
        """レンジダウンロードの開始日（today - range_days）."""
        return date.today() - timedelta(days=self.range_days)

    @property
    def date_range_to(self) -> date:
        """レンジダウンロードの終了日（today）."""
        return date.today()


def parse_args(argv: list[str] | None = None) -> AppConfig:
    """CLI 引数をパースして AppConfig を返す."""
    parser = argparse.ArgumentParser(
        description="日別売上集計データ自動ダウンロード",
    )
    parser.add_argument(
        "--date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="対象日 (YYYY-MM-DD)。デフォルト: 前日。--date-from/--date-to と併用不可",
    )
    parser.add_argument(
        "--date-from",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="対象期間の開始日 (YYYY-MM-DD)。--date-to と組み合わせて使用",
    )
    parser.add_argument(
        "--date-to",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="対象期間の終了日 (YYYY-MM-DD)。--date-from と組み合わせて使用",
    )
    parser.add_argument(
        "--site",
        type=lambda s: s.split(","),
        default=None,
        help="対象サイト (カンマ区切り: rakuten,yahoo,amazon,shopify,next_engine)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="ブラウザを表示して実行（デバッグ用）",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="リトライ回数 (デフォルト: 3)",
    )
    parser.add_argument(
        "--date-mode",
        choices=["shipment", "order"],
        default="shipment",
        help="Date field to search: shipment (出荷確定日) or order (受注日)",
    )
    parser.add_argument(
        "--range-days",
        type=int,
        default=0,
        help="Download N days range instead of single date (NE only, 0=disabled)",
    )

    args = parser.parse_args(argv)

    # 日付の決定: --date と --date-from/--date-to は排他
    if args.date and (args.date_from or args.date_to):
        parser.error("--date と --date-from/--date-to は同時に指定できません")

    if args.date_from or args.date_to:
        if not (args.date_from and args.date_to):
            parser.error("--date-from と --date-to は両方指定してください")
        if args.date_from > args.date_to:
            parser.error("--date-from は --date-to 以前の日付にしてください")
        # 各日を個別にリスト化（古い順）
        target_dates: list[date] = []
        d = args.date_from
        while d <= args.date_to:
            target_dates.append(d)
            d += timedelta(days=1)
    elif args.date:
        target_dates = [args.date]
    else:
        target_dates = [date.today() - timedelta(days=1)]

    sites = args.site if args.site else list(SITES)
    for s in sites:
        if s not in SITES:
            parser.error(f"不明なサイト: {s}。有効値: {', '.join(SITES)}")

    username = os.environ.get("USERNAME") or os.environ.get("USER", "")
    if not username:
        parser.error("環境変数 USERNAME が設定されていません")

    # range_days > 0 の場合、date_mode を "order" に強制
    date_mode = args.date_mode
    range_days = args.range_days
    if range_days > 0:
        date_mode = "order"

    return AppConfig(
        username=username,
        target_dates=target_dates,
        target_sites=sites,
        max_retries=args.retries,
        headless=not args.no_headless,
        date_mode=date_mode,
        range_days=range_days,
    )
