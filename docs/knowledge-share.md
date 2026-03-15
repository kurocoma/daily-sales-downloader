# 日別売上集計データダウンローダー — ナレッジ共有ドキュメント

## 1. プロジェクト概要

4つのECプラットフォーム（楽天市場・Yahoo Shopping・Amazon Seller Central・ネクストエンジン）から日別の売上データを自動ダウンロードするCLIツール。

- **言語**: Python 3.12+
- **ブラウザ自動化**: Playwright (async API)
- **パッケージ管理**: uv
- **認証情報**: xlsx ファイルから読み取り（dotenv で機密パスを外部化）

---

## 2. ディレクトリ構成

```
daily-sales-downloader/
├── .claude/                         # Claude Code 設定
│   ├── hooks/                       # pre/post ツールフック
│   ├── skills/                      # 再利用可能スキル（後述）
│   ├── settings.json
│   └── project-identity.example.json
├── .env.example                     # 環境変数テンプレート
├── .gitignore
├── .mcp.json                        # MCP サーバー設定（playwright, browser-use）
├── CLAUDE.md                        # プロジェクトルール
├── AGENTS.md                        # エージェント向け指示
├── pyproject.toml                   # uv / pip 依存定義
├── uv.lock
│
├── docs/
│   ├── spec.md                      # 要件定義書
│   ├── detailed-design.md           # 詳細設計書
│   ├── knowledge-share.md           # ← このファイル
│   └── ID・PW.xlsx                  # 認証情報（gitignore 対象）
│
├── plans/
│   └── plan.md                      # 実装計画・フェーズ管理
│
├── src/
│   ├── __init__.py
│   ├── main.py                      # CLI エントリポイント
│   ├── config.py                    # 設定管理（CLI引数パース）
│   ├── credential.py                # xlsx → SiteCredential 読み取り
│   ├── downloader/
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseDownloader（共通基底クラス）
│   │   ├── rakuten.py               # 楽天市場
│   │   ├── yahoo.py                 # Yahoo Shopping
│   │   ├── amazon.py                # Amazon Seller Central
│   │   └── next_engine.py           # ネクストエンジン
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                # 日次ログ + 自動クリーンアップ
│       └── path_resolver.py         # 保存先パス生成
│
├── tests/
│   ├── test_config.py
│   ├── test_credential.py
│   └── test_path_resolver.py
│
├── data/                            # 実行時データ（gitignore 対象）
│   └── cookies/                     # Cookie / storage_state 保存
│       ├── rakuten.json
│       ├── yahoo.json
│       ├── next_engine.json
│       └── amazon_profile/          # Amazon は persistent context
│
└── logs/                            # 実行ログ（gitignore 対象）
    ├── YYYY-MM-DD.log
    └── screenshots/                 # エラー時スクリーンショット
```

---

## 3. アーキテクチャ

### 3.1 処理フロー

```
CLI引数パース → .env読込 → 認証情報(xlsx)読込
  → Playwright起動
    → サイトループ（外側）
      → Cookie復元 → ログイン（1回/サイト）
        → 日付ループ（内側）
          → 検索条件設定 → データ0件チェック → ダウンロード → ファイル保存
        → Cookie保存
    → 結果サマリー出力
```

**ポイント**: サイトファースト・日付セカンドの二重ループ。ログインは各サイト1回のみで、同一セッション内で日付を切り替えてDL。画面遷移を最小化しエラーリスクを低減。

### 3.2 BaseDownloader パターン

```python
class BaseDownloader(ABC):
    # 共通メソッド
    async def run()                    # 単一日付実行
    async def run_multi_dates(dates)   # 複数日付実行（ログイン1回）
    async def wait_and_download_file() # page.expect_download ラッパー
    async def save_downloaded_file()   # 一時ファイル → 最終保存先に移動

    # サブクラスで実装
    @abstractmethod async def login()
    @abstractmethod async def download() -> list[Path]
```

### 3.3 Cookie 管理

| サイト | 方式 | 理由 |
|--------|------|------|
| 楽天・Yahoo・NE | `context.storage_state()` で JSON 保存/復元 | 標準的な Cookie + localStorage |
| Amazon | `launch_persistent_context(user_data_dir=...)` | 2FA + 高度なセッション管理のため永続プロファイルが必要 |

### 3.4 データ0件ハンドリング

各サイトでデータが0件の場合、タイムアウトを待たずにスキップする:

| サイト | 判定テキスト | 判定タイミング |
|--------|-------------|---------------|
| 楽天 | `この条件でのデータ件数は0件です` | 「データを作成する」クリック後 |
| Yahoo | `該当する注文がありません` | DL画面遷移後 |
| Amazon (トランザクション) | `結果が見つかりませんでした` | 「更新」クリック後 |
| ネクストエンジン | `結果はありませんでした` | 検索実行後 |

---

## 4. 各サイトのログインフロー詳細

### 4.1 楽天市場（4画面構成）

```
1画面目: R-Login ID + パスワード
  → submit ボタンクリック → ナビゲーション待機

2画面目a: 楽天会員ID入力 → 「次へ」
  ※ Cookie復元時はID記憶済みでスキップされる場合あり

2画面目b: パスワード入力 → 「次へ」or「ログイン」
  → force click で overlay を回避

3画面目: 「次へ」ボタン（表示されない場合あり → try/except でスキップ）

4画面目: RMS利用確認（表示されない場合あり → try/except でスキップ）
```

**認証情報**: 3種類必要（管理者用・ユーザー認証用・CSVダウンロード用）

### 4.2 Yahoo Shopping（パスキー対応）

```
1画面目: handle（ID）入力 → 「次へ」
  ※ Cookie復元時はログイン画面自体がスキップ

2画面目: パスキー画面が出る場合あり
  → 「他の方法でログイン」→「パスワード」選択
  → パスワード入力 → 「ログイン」
```

**ストアID**: 環境変数 `YAHOO_STORE_ID` で管理（URL構築に使用）

### 4.3 Amazon Seller Central（2FA必須）

```
Cookie復元 → Seller Central にアクセス
  → signin にリダイレクト？
    → headless なら RuntimeError（手動対応が必要）
    → no-headless なら ID/PW 自動入力 → 2FA は手動待機（最大10分）

アカウント選択画面 → 「アカウントを選択」（表示される場合）
```

**重要**: Amazon は `launch_persistent_context` を使用。初回は `--no-headless` で手動ログインが必須。

### 4.4 ネクストエンジン（お知らせページ対応）

```
ログインページ → ID + パスワード入力 → 「ログイン」
  ※ Cookie復元時はログインフォーム非表示 → スキップ

お知らせページ（不定期表示）
  → 「すべて既読にする」ボタン
  → confirm ダイアログ → dialog.accept() で自動承認

「メイン機能」リンクをクリック → main ドメインへ遷移
```

**特殊処理**:
- お知らせページはログイン直後に不定期表示されるため、`_handle_news_page()` で処理
- `page.on("dialog", lambda dialog: dialog.accept())` でブラウザダイアログを自動承認
- モーダル backdrop が残る問題 → `evaluate()` で手動除去:
  ```python
  await self.page.evaluate(
      'document.querySelectorAll(".modal-backdrop").forEach(e => e.remove())'
  )
  ```

---

## 5. ダウンロードフロー詳細

### 5.1 ネクストエンジン — 購入者データ

```
受注一覧へ遷移（search_condi=17）
  → 「詳細検索」ダイアログ開く
  → 「クリア」で条件リセット
  → 受注キャンセル区分 = "0"（有効な受注）
  → 出荷確定日 from/to に日付入力
  → 検索実行
  → backdrop 除去（evaluate）
  → データ0件チェック
  → テーブル表示待機
  → ダウンロードリンクをクリック
```

### 5.2 ネクストエンジン — 商品情報データ

```
受注一覧へ再度遷移 → 同条件で検索
  → 「全て選択」チェック
  → 「明細一覧」クリック
  → モーダル:「伝票明細単位で出力」選択
  → 「開く」→ 新タブが開く（context.expect_page）
  → 新タブでダウンロードリンクをクリック
  → 新タブを閉じる
```

### 5.3 Amazon — Shadow DOM / Web Components 操作

Amazon Seller Central は `kat-dropdown`, `kat-date-picker` 等のカスタム Web Components を使用。通常の Playwright セレクタでは操作できないため、JavaScript で直接操作:

```python
# kat-dropdown の値設定
await self.page.evaluate("""
    () => {
        const dropdown = document.querySelector('kat-dropdown.daily-time-picker...');
        if (dropdown) {
            dropdown.value = '7';
            dropdown.dispatchEvent(new CustomEvent('change', {
                bubbles: true, composed: true
            }));
        }
    }
""")

# kat-date-picker の日付設定
await self.page.evaluate(f"""
    () => {{
        const picker = document.querySelector('kat-date-picker[name="startDate"]');
        if (!picker) return;
        picker.value = "{date_str}";
        picker.dispatchEvent(new CustomEvent('change', {{
            bubbles: true, composed: true,
            detail: {{ isoValue: "{iso_str}", value: "{date_str}" }}
        }}));
    }}
""")
```

**ツアーオーバーレイ除去**: Amazon は初回訪問時に Joyride ツアーが表示され操作をブロックするため除去が必要:
```python
await self.page.evaluate(
    'document.querySelectorAll("#react-joyride-portal, .react-joyride__overlay").forEach(e => e.remove())'
)
```

---

## 6. 再利用可能な Claude Code Skills

### 6.1 playwright-python

Playwright を Python/uv プロジェクトで使うためのスキル。ログインフロー、スクリーンショット取得、E2Eサポートに対応。

**適用場面**: ブラウザ自動化のコード実装が必要な場合

### 6.2 web-automation-stack

タスクに応じた最適なブラウザ自動化スタックを選択するルーティングガイド:

| スタック | 使い所 |
|----------|--------|
| Playwright コード | リポジトリ/CI に残す自動化 |
| Playwright MCP | 対話的なブラウザ検査・スクリーンショット |
| Browser Use MCP | オープンエンドな自然言語タスク |
| Next.js MCP | Next.js 16+ 開発サーバーのデバッグ |

### 6.3 browser-regression

ブラウザ回帰テスト — 表示差分・壊れたフロー・エビデンスを要約するスキル。

---

## 7. 他プロジェクトへの転用ガイド

### 7.1 新しいサイトを追加する場合

1. `src/downloader/` に新しいファイルを作成
2. `BaseDownloader` を継承し `login()` と `download()` を実装
3. `src/main.py` の `_register_downloaders()` にクラスを登録
4. `src/config.py` の `SITES` タプルにサイト名を追加
5. `src/credential.py` の `_SITE_KEY_MAP` に xlsx のラベル → 内部キーのマッピングを追加
6. `src/utils/path_resolver.py` に `DownloadTarget` と保存パスを追加

### 7.2 ネクストエンジン連携を別プロジェクトで使う場合

必要なもの:
- ログイン処理: `next_engine.py` の `login()` + `_handle_news_page()`
- Cookie 管理: `main.py` の `storage_state` 保存/復元パターン
- モーダル backdrop 除去: `evaluate()` パターン

注意点:
- ネクストエンジンは「base ドメイン（認証）」→「main ドメイン（業務）」の2ドメイン構成
- ログイン後に `get_by_role("link", name="メイン機能")` で main へ遷移が必要
- お知らせページは不定期出現 → `_handle_news_page()` で堅牢に処理

### 7.3 共通パターン集

| パターン | 用途 | コード例の場所 |
|----------|------|---------------|
| Cookie 復元 → ログインスキップ | セッション再利用 | 全 downloader の `login()` |
| `page.expect_download` ラッパー | ファイルDL | `base.py:wait_and_download_file()` |
| `context.expect_page` | 新タブ処理 | `next_engine.py:_search_and_download_product()` |
| `page.evaluate()` で Shadow DOM 操作 | Web Components | `amazon.py:_download_all_order_report()` |
| `page.on("dialog", ...)` | confirm/alert 自動承認 | `next_engine.py:_handle_news_page()` |
| データ0件チェック → 早期 return | タイムアウト回避 | 全 downloader の `download()` |
| エラー時スクリーンショット自動保存 | デバッグ | `base.py:_save_screenshot()` |
| 古いログ自動クリーンアップ | 運用 | `logger.py:_cleanup_old_logs()` |

---

## 8. 環境変数

| 変数名 | 用途 | デフォルト |
|--------|------|-----------|
| `DL_BASE_PATH` | ダウンロード保存先ベースパス | `C:\Users\{username}\日別売上集計` |
| `YAHOO_STORE_ID` | Yahoo ストアクリエイターPro のストアID | `your_store_id` |

---

## 9. CLI 使用例

```bash
# 前日のデータを全サイトからDL（デフォルト）
uv run python -m src.main

# 特定日を指定
uv run python -m src.main --date 2026-03-14

# 期間指定（複数日）
uv run python -m src.main --date-from 2026-03-13 --date-to 2026-03-15

# 特定サイトのみ
uv run python -m src.main --site rakuten,yahoo

# ブラウザ表示モード（デバッグ / 初回ログイン用）
uv run python -m src.main --site amazon --no-headless
```

---

## 10. テスト実績

| 日付 | 楽天 | Yahoo | Amazon (全注文) | Amazon (トランザクション) | NE (購入者) | NE (商品) |
|------|------|-------|----------------|------------------------|------------|----------|
| 3/13 | OK | OK | OK | OK | OK | OK |
| 3/14 | OK (0件) | OK (0件) | OK | OK (0件) | OK (0件) | OK (0件) |
| 3/15 | OK (0件) | OK (0件) | OK | OK (0件) | OK (0件) | OK (0件) |

ヘッドレスモードで 3日 × 4サイト = 12件すべて成功（0件含む）。
