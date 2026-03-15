"""credential.py のテスト."""

from pathlib import Path

import pytest

from src.credential import load_credentials
from src.config import CREDENTIAL_PATH


def test_load_credentials_from_real_file():
    """実際の xlsx ファイルから読み込めること."""
    if not CREDENTIAL_PATH.exists():
        pytest.skip("ID・PW.xlsx が存在しません")

    creds = load_credentials(CREDENTIAL_PATH)
    assert len(creds) > 0

    # 必要なキーが揃っているか
    expected_keys = {"rakuten_admin", "rakuten_user", "yahoo", "amazon", "next_engine"}
    assert expected_keys.issubset(creds.keys()), f"不足キー: {expected_keys - creds.keys()}"

    # 各認証情報が空でないこと
    for key, cred in creds.items():
        assert cred.login_id, f"{key} の login_id が空です"
        assert cred.password, f"{key} の password が空です"


def test_file_not_found():
    """存在しないファイルで FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_credentials(Path("/nonexistent/file.xlsx"))
