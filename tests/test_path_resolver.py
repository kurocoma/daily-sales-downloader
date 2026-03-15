"""path_resolver.py のテスト."""

from datetime import date
from pathlib import Path

from src.utils.path_resolver import DownloadTarget, resolve_download_path


BASE = Path(r"C:\Users\test\base")
DATE = date(2026, 3, 11)


def test_rakuten():
    p = resolve_download_path(BASE, DownloadTarget.RAKUTEN, DATE)
    assert p == BASE / "2026" / "楽天" / "日別売上データ" / "3月" / "20260311.csv"


def test_yahoo_order():
    p = resolve_download_path(BASE, DownloadTarget.YAHOO_ORDER, DATE)
    assert p == BASE / "2026" / "yahoo" / "order" / "3月" / "20260311_order.csv"


def test_yahoo_item():
    p = resolve_download_path(BASE, DownloadTarget.YAHOO_ITEM, DATE)
    assert p == BASE / "2026" / "yahoo" / "item" / "3月" / "20260311_item.csv"


def test_amazon_all_order():
    p = resolve_download_path(BASE, DownloadTarget.AMAZON_ALL_ORDER, DATE)
    assert p == BASE / "2026" / "amazon" / "全注文レポート" / "3月" / "AllOrderReport_20260311.txt"


def test_amazon_transaction():
    p = resolve_download_path(BASE, DownloadTarget.AMAZON_TRANSACTION, DATE)
    expected = BASE / "2026" / "amazon" / "日別トランザクション" / "3月" / "20260311_20260311の期間の取引.csv"
    assert p == expected


def test_ne_buyer():
    p = resolve_download_path(BASE, DownloadTarget.NE_BUYER, DATE)
    assert p == BASE / "2026" / "ネクストエンジン" / "購入者データ" / "20260311.csv"


def test_ne_product():
    p = resolve_download_path(BASE, DownloadTarget.NE_PRODUCT, DATE)
    assert p == BASE / "2026" / "ネクストエンジン" / "商品情報データ" / "20260311.csv"


def test_year_month_change():
    """年末 → 翌年1月のパス."""
    d = date(2026, 12, 31)
    p = resolve_download_path(BASE, DownloadTarget.RAKUTEN, d)
    assert "2026" in str(p)
    assert "12月" in str(p)

    d2 = date(2027, 1, 1)
    p2 = resolve_download_path(BASE, DownloadTarget.RAKUTEN, d2)
    assert "2027" in str(p2)
    assert "1月" in str(p2)
