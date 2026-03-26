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
    SHOPIFY = "shopify"
    NE_BUYER = "ne_buyer"
    NE_PRODUCT = "ne_product"
    NE_BUYER_ORDER_DATE = "ne_buyer_order_date"
    NE_PRODUCT_ORDER_DATE = "ne_product_order_date"
    NE_BUYER_RANGE = "ne_buyer_range"
    NE_PRODUCT_RANGE = "ne_product_range"


# ベースパスからの相対パス定義
# {year}, {month} はフォーマット時に置換
_PATH_MAP: dict[DownloadTarget, str] = {
    DownloadTarget.RAKUTEN: r"楽天\日別売上データ\{month}月",
    DownloadTarget.YAHOO_ORDER: r"yahoo\order\{month}月",
    DownloadTarget.YAHOO_ITEM: r"yahoo\item\{month}月",
    DownloadTarget.AMAZON_ALL_ORDER: r"amazon\全注文レポート\{month}月",
    DownloadTarget.AMAZON_TRANSACTION: r"amazon\日別トランザクション\{month}月",
    DownloadTarget.SHOPIFY: r"shopify\{month}月",
    DownloadTarget.NE_BUYER: r"ネクストエンジン\購入者データ",
    DownloadTarget.NE_PRODUCT: r"ネクストエンジン\商品情報データ",
    DownloadTarget.NE_BUYER_ORDER_DATE: r"ネクストエンジン\注文日ベース\購入者データ",
    DownloadTarget.NE_PRODUCT_ORDER_DATE: r"ネクストエンジン\注文日ベース\商品情報データ",
    DownloadTarget.NE_BUYER_RANGE: r"ネクストエンジン\受注日レンジ",
    DownloadTarget.NE_PRODUCT_RANGE: r"ネクストエンジン\受注日レンジ",
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
        case DownloadTarget.SHOPIFY:
            return f"{ds}.csv"
        case (
            DownloadTarget.NE_BUYER
            | DownloadTarget.NE_PRODUCT
            | DownloadTarget.NE_BUYER_ORDER_DATE
            | DownloadTarget.NE_PRODUCT_ORDER_DATE
        ):
            return f"{ds}.csv"
        case DownloadTarget.NE_BUYER_RANGE | DownloadTarget.NE_PRODUCT_RANGE:
            # Range targets require date_range_from; this fallback should
            # not be reached when using resolve_range_download_path().
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


def resolve_range_download_path(
    base: Path,
    target: DownloadTarget,
    date_from: date,
    date_to: date,
) -> Path:
    """レンジダウンロード用の保存先フルパスを返す.

    Args:
        base: ダウンロード保存先ベースパス（年ディレクトリの親）
        target: ダウンロード対象 (NE_BUYER_RANGE / NE_PRODUCT_RANGE)
        date_from: 範囲開始日
        date_to: 範囲終了日

    Returns:
        保存先のフルパス（ディレクトリ + ファイル名）
    """
    year = str(date_to.year)
    sub_path = _PATH_MAP[target]
    ds_from = date_from.strftime("%Y%m%d")
    ds_to = date_to.strftime("%Y%m%d")

    if target == DownloadTarget.NE_BUYER_RANGE:
        filename = f"buyer_{ds_from}_{ds_to}.csv"
    elif target == DownloadTarget.NE_PRODUCT_RANGE:
        filename = f"product_{ds_from}_{ds_to}.csv"
    else:
        raise ValueError(f"resolve_range_download_path does not support target: {target}")

    return base / year / sub_path / filename


def ensure_download_dir(path: Path) -> None:
    """保存先ディレクトリが存在しなければ作成する."""
    path.parent.mkdir(parents=True, exist_ok=True)
