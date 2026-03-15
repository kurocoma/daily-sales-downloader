# 詳細設計書 — 日別売上集計データ自動ダウンロード

## 1. 技術スタック

| 項目 | 選定 |
|------|------|
| 言語 | Python 3.12+ |
| ブラウザ自動化 | Playwright (Python) |
| パッケージ管理 | uv |
| 認証情報読み取り | openpyxl (xlsx → dict) |
| スケジューリング | Windows タスクスケジューラ |
| ログ | Python logging → ファイル + コンソール |

## 2. ディレクトリ構成

```
日別売上集計データダウンロード/
├── .gitignore
├── CLAUDE.md
├── AGENTS.md
├── pyproject.toml
├── docs/
│   ├── spec.md              # 要件定義書
│   ├── detailed-design.md   # 本ファイル
│   └── ID・PW.xlsx          # 認証情報（git管理外）
├── plans/
│   └── plan.md              # 実装計画
├── src/
│   ├── __init__.py
│   ├── main.py              # エントリポイント（CLI）
│   ├── config.py            # 設定・パス解決
│   ├── credential.py        # xlsx から ID/PW 読み取り
│   ├── downloader/
│   │   ├── __init__.py
│   │   ├── base.py          # 基底クラス（共通ログイン・DL・リトライ）
│   │   ├── rakuten.py       # 楽天市場
│   │   ├── yahoo.py         # Yahoo Shopping
│   │   ├── amazon.py        # Amazon（全注文 + トランザクション）
│   │   └── next_engine.py   # ネクストエンジン
│   └── utils/
│       ├── __init__.py
│       ├── path_resolver.py  # 保存先パス生成
│       └── logger.py          # ログ設定
├── tests/
│   ├── test_config.py
│   ├── test_credential.py
│   └── test_path_resolver.py
└── logs/                     # 実行ログ（git管理外）
```

## 3. モジュール設計

### 3.1 config.py — 設定管理

```python
@dataclass
class AppConfig:
    username: str           # Windows ユーザー名（環境変数）
    base_path: Path         # ダウンロード保存ベースパス
    credential_path: Path   # ID・PW.xlsx のパス
    target_date: date       # ダウンロード対象日（デフォルト: 前日）
    max_retries: int = 3    # リトライ回数
    retry_delay: float = 5.0  # リトライ間隔（秒、指数バックオフ）
    headless: bool = True   # ヘッドレスモード
```

- 環境変数 `USERNAME` からユーザー名を取得
- CLI 引数で `--date YYYY-MM-DD` による日付指定（リカバリー用）
- CLI 引数で `--site rakuten,yahoo,amazon,ne` による対象指定

### 3.2 credential.py — 認証情報管理

```python
def load_credentials(xlsx_path: Path) -> dict[str, SiteCredential]
```

- openpyxl で xlsx を読み取り
- サイトごとの ID/PW を `SiteCredential(id, password)` として返す
- xlsx のシート構造は実装時に実ファイルを確認して対応

### 3.3 downloader/base.py — 基底ダウンローダー

```python
class BaseDownloader(ABC):
    def __init__(self, config: AppConfig, credential: SiteCredential, page: Page): ...

    async def run(self) -> DownloadResult:
        """メインフロー: ログイン → ダウンロード → 保存 → 検証"""
        try:
            await self.login()
            files = await self.download()
            await self.save(files)
            return DownloadResult(success=True, files=files)
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    @abstractmethod
    async def login(self): ...

    @abstractmethod
    async def download(self) -> list[Path]: ...

    async def save(self, files: list[Path]):
        """DL ファイルを正しい保存先にリネーム・移動"""
        ...

    def resolve_save_path(self) -> Path:
        """対象日から保存先ディレクトリを算出"""
        ...
```

### 3.4 各モール Downloader

各クラスは `BaseDownloader` を継承し、`login()` と `download()` を実装。

- **RakutenDownloader**: ログイン4画面 → CSV DL ページ → 条件設定 → DL
- **YahooDownloader**: ログイン2画面 → 注文管理 → 詳細検索 → DL (2ファイル)
- **AmazonDownloader**: ログイン(2FA) → 全注文レポート + 日別トランザクション
- **NextEngineDownloader**: ログイン → お知らせ処理 → 受注検索 → DL → 明細DL

### 3.5 path_resolver.py — パス生成

```python
def resolve_download_path(
    base: Path, site: str, data_type: str, target_date: date
) -> Path:
    """
    サイト・データ種別ごとにパスとファイル名を生成。

    ファイル名パターン:
      楽天:                  YYYYMMDD.csv
      Yahoo (注文):          YYYYMMDD_order.csv
      Yahoo (商品):          YYYYMMDD_item.csv
      Amazon (全注文):       AllOrderReport_YYYYMMDD.txt
      Amazon (トランザクション): YYYYMMDD_YYYYMMDDの期間の取引.csv
      NE (購入者/商品情報):  YYYYMMDD.csv

    例: base / "2026" / "楽天" / "日別売上データ" / "3月" / "20260311.csv"
    """
```

### 3.6 main.py — CLI エントリポイント

```python
async def main():
    config = parse_args()
    credentials = load_credentials(config.credential_path)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=config.headless)

        results = {}
        for site in config.target_sites:
            for attempt in range(config.max_retries):
                result = await run_site(browser, config, credentials, site)
                if result.success:
                    break
                await asyncio.sleep(config.retry_delay * (2 ** attempt))
            results[site] = result

        await browser.close()

    report(results)
    if any(not r.success for r in results.values()):
        sys.exit(1)
```

## 4. エラーハンドリング・リカバリー

| シナリオ | 対処 |
|---------|------|
| ログイン失敗 | リトライ（最大3回）→ 通知 |
| ページ遷移タイムアウト | リトライ（待機時間延長）→ 通知 |
| セレクタ不在 | スクリーンショット保存 → 通知 |
| DLファイル 0byte | エラー扱い → リトライ |
| ネットワークエラー | リトライ（指数バックオフ）→ 通知 |
| Amazon 2FA 要求 | Cookie 保存で回避。失効時は通知して手動対応 |
| 部分失敗 | 成功したサイトはスキップし、失敗サイトのみ再実行可能 |

### リカバリーコマンド例

```bash
# 特定日・特定サイトだけ再実行
python -m src.main --date 2026-03-10 --site rakuten,amazon
```

## 5. ログ設計

```
logs/
├── 2026-03-12.log          # 日次ログ
└── screenshots/
    └── 2026-03-12_rakuten_error.png  # エラー時スクリーンショット
```

ログフォーマット:
```
2026-03-12 02:00:05 [INFO]  rakuten: ログイン成功
2026-03-12 02:00:15 [INFO]  rakuten: CSV DL ページ遷移完了
2026-03-12 02:00:30 [INFO]  rakuten: ダウンロード完了 → 2026-03-11.csv
2026-03-12 02:01:00 [ERROR] yahoo: ログイン失敗 (attempt 1/3) - TimeoutError
```

## 6. Cookie / セッション管理

- Playwright の `browser_context.storage_state()` で Cookie を保存
- 次回実行時に読み込み、ログインをスキップ可能
- Amazon 2FA のセッション維持に特に有効
- Cookie ファイルは `data/cookies/` に保存（git 管理外）

## 7. 確認事項（実装進行中に解決）

→ [docs/spec.md](./spec.md) の「7. 確認事項」セクションを参照
