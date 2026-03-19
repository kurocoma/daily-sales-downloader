"""認証情報管理 — xlsx から ID/PW を読み取る."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl


@dataclass(frozen=True)
class SiteCredential:
    """サイトごとの認証情報."""

    site_name: str
    login_id: str
    password: str
    note: str = ""


# xlsx の A 列の値 → 内部キーのマッピング
_SITE_KEY_MAP: dict[str, str] = {
    "楽天(管理)": "rakuten_admin",
    "楽天(ユーザー認証)": "rakuten_user",
    "楽天(ダウンロード用)": "rakuten_csv",
    "Yahoo": "yahoo",
    "Amazon": "amazon",
    "Shopify": "shopify",
    "ネクストエンジン": "next_engine",
}


def load_credentials(xlsx_path: Path) -> dict[str, SiteCredential]:
    """xlsx ファイルから認証情報を読み取って返す.

    Returns:
        dict[str, SiteCredential]: キーはサイト内部名
    """
    if not xlsx_path.exists():
        raise FileNotFoundError(f"認証情報ファイルが見つかりません: {xlsx_path}")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    try:
        ws = wb.active
        if ws is None:
            raise ValueError("xlsx にアクティブシートがありません")

        credentials: dict[str, SiteCredential] = {}
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            site_label = str(row[0] or "").strip()
            login_id = str(row[1] or "").strip()
            password = str(row[2] or "").strip()
            note = str(row[3] or "").strip() if len(row) > 3 and row[3] else ""

            if not site_label or not login_id:
                continue

            key = _SITE_KEY_MAP.get(site_label)
            if key is None:
                continue

            credentials[key] = SiteCredential(
                site_name=site_label,
                login_id=login_id,
                password=password,
                note=note,
            )

        return credentials
    finally:
        wb.close()
