"""保存先パス生成 — サイト・データ種別ごとにパスとファイル名を解決する."""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path


class DownloadTarget(Enum):
    """ダウンロード対象の識別子."""

    RAKUTEN = "rakuten"
    YAHOO_ORDER = "yahoo_order"
    YAHOO_ITEM = "yahoo_item"
    AMAZON_ALL_ORDER = "amazon_all_order"
    AMAZON_TRANSACTION = "amazon_transaction"
    NE_BUYER = "ne_buyer"
    NE_PRODUCT = "ne_product"


# ベースパスからの相対パス定義
# {year}, {month} はフォーマット時に置換
_PATH_MAP: dict[DownloadTarget, str] = {
    DownloadTarget.RAKUTEN: r"楽天\日別売上データ\{month}月",
    DownloadTarget.YAHOO_ORDER: r"yahoo\order\{month}月",
    DownloadTarget.YAHOO_ITEM: r"yahoo\item\{month}月",
    DownloadTarget.AMAZON_ALL_ORDER: r"amazon\全注文レポート\{month}月",
    DownloadTarget.AMAZON_TRANSACTION: r"amazon\日別トランザクション\{month}月",
    DownloadTarget.NE_BUYER: r"ネクストエンジン\購入者データ",
    DownloadTarget.NE_PRODUCT: r"ネクストエンジン\商品情報データ",
}


def _format_filename(target: DownloadTarget, target_date: date) -> str:
    """対象に応じたファイル名を生成する."""
    ds = target_date.strftime("%Y%m%d")

    match target:
        case DownloadTarget.RAKUTEN:
            return f"{ds}.csv"
        case DownloadTarget.YAHOO_ORDER:
            return f"{ds}_order.csv"
        case DownloadTarget.YAHOO_ITEM:
            return f"{ds}_item.csv"
        case DownloadTarget.AMAZON_ALL_ORDER:
            return f"AllOrderReport_{ds}.txt"
        case DownloadTarget.AMAZON_TRANSACTION:
            return f"{ds}_{ds}の期間の取引.csv"
        case DownloadTarget.NE_BUYER | DownloadTarget.NE_PRODUCT:
            return f"{ds}.csv"


def resolve_download_path(
    base: Path,
    target: DownloadTarget,
    target_date: date,
) -> Path:
    """ダウンロード保存先のフルパスを返す.

    Args:
        base: ダウンロード保存先ベースパス（年ディレクトリの親）
        target: ダウンロード対象
        target_date: 対象日

    Returns:
        保存先のフルパス（ディレクトリ + ファイル名）
    """
    year = str(target_date.year)
    month = str(target_date.month)

    sub_path = _PATH_MAP[target].format(month=month)
    filename = _format_filename(target, target_date)

    return base / year / sub_path / filename


def ensure_download_dir(path: Path) -> None:
    """保存先ディレクトリが存在しなければ作成する."""
    path.parent.mkdir(parents=True, exist_ok=True)
