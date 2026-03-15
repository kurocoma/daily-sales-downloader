"""config.py のテスト."""

from datetime import date, timedelta

from src.config import parse_args


def test_default_date_is_yesterday():
    config = parse_args([])
    assert config.target_date == date.today() - timedelta(days=1)


def test_custom_date():
    config = parse_args(["--date", "2026-03-10"])
    assert config.target_date == date(2026, 3, 10)


def test_default_sites():
    config = parse_args([])
    assert config.target_sites == ["rakuten", "yahoo", "amazon", "next_engine"]


def test_custom_sites():
    config = parse_args(["--site", "rakuten,yahoo"])
    assert config.target_sites == ["rakuten", "yahoo"]


def test_headless_default():
    config = parse_args([])
    assert config.headless is True


def test_no_headless():
    config = parse_args(["--no-headless"])
    assert config.headless is False


def test_download_base_contains_username():
    config = parse_args([])
    assert config.username in str(config.download_base)
    assert "日別売上集計" in str(config.download_base)
