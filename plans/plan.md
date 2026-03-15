# 詳細設計書 — 日別売上集計データ自動ダウンロード

## フェーズ 1: 基盤 ✅ 完了

- [x] プロジェクト初期化（pyproject.toml, uv, Playwright インストール）
- [x] `src/config.py` — CLI 引数パース、設定管理
- [x] `src/credential.py` — xlsx 読み取り（openpyxl）
- [x] `src/utils/path_resolver.py` — 保存先パス生成
- [x] `src/downloader/base.py` — 基底クラス（ログ・スクリーンショット・エラーハンドリング）

## フェーズ 2: 各モール実装 ✅ 完了

- [x] `src/downloader/rakuten.py` — 楽天（4画面ログイン + CSV DL）
- [x] `src/downloader/yahoo.py` — Yahoo（注文データ + 商品データ DL）
- [x] `src/downloader/amazon.py` — Amazon 全注文レポート + 日別トランザクション
- [x] `src/downloader/next_engine.py` — ネクストエンジン（購入者 + 商品情報）

## フェーズ 3: エラーハンドリング・Cookie 対応 ✅ 完了

- [x] Cookie 対応ログイン — 全4サイトでセッション復元・ログインスキップ
- [x] 楽天「認証が必要です」リトライ（最大3回）
- [x] Amazon 2FA — persistent_context でデバイス記憶
- [x] Amazon 全注文レポート「処理中」ポーリング待機
- [x] エラー時スクリーンショット自動保存
- [x] ログシステム強化（スタックトレース、URL/タイトル、経過時間）
- [x] ログ自動クリーンアップ（30日超）

## フェーズ 4: 複数日付サポート ✅ 完了

- [x] `--date-from` / `--date-to` CLI 引数追加
- [x] `AppConfig.target_dates` を `list[date]` に変更
- [x] サイトループ → 日付ループの処理フロー
- [x] 日付別・サイト別の結果サマリー

## フェーズ 5: データ0件ハンドリング ✅ 完了

- [x] 楽天 — 「この条件でのデータ件数は0件です」判定 → 空リスト返却
- [x] Yahoo — 「該当する注文がありません」判定 → 空リスト返却
- [x] Amazon トランザクション — 「結果が見つかりませんでした」判定 → None返却
- [x] NE 購入者/商品情報 — 「結果はありませんでした」判定 → None返却
- [x] デバッグ用スクリーンショット削除（amazon.py）

## フェーズ 6: 自動化検出回避・セッション維持 ✅ 完了

- [x] `playwright-stealth` 導入 — 全サイトのコンテキストに `Stealth().apply_stealth_async()` 適用
- [x] Amazon `--disable-blink-features=AutomationControlled` 追加
- [x] `src/session_refresh.py` — Amazon セッション定期リフレッシュスクリプト
- [x] タスクスケジューラ `AmazonSessionRefresh` 登録（2時間ごと）

## フェーズ 7: NE Cookie バナー対応 ✅ 完了

- [x] `_dismiss_cookie_banner()` — Cookie 同意バナー（`#cm-ov` オーバーレイ）を閉じる処理
- [x] 同意ボタンクリック or JS による要素除去のフォールバック

## フェーズ 8: スケジューリング・本番運用 ✅ 完了

- [x] タスクスケジューラ `DailySalesDownload` 登録（毎朝 6:00）
- [x] 失敗時リトライ設定（1時間ごと、最大3回、9:00 までにカバー）
- [x] タスクスケジューラからの実行テスト — 全4サイト成功確認
- [ ] 1週間の本番試行 → 安定性確認

---

## アーキテクチャ

```
src/
├── main.py              # CLI エントリポイント・メインループ（playwright-stealth 適用）
├── config.py            # AppConfig（CLI引数・設定管理）
├── credential.py        # xlsx からの認証情報読み取り
├── session_refresh.py   # Amazon セッション定期リフレッシュ
├── utils/
│   ├── path_resolver.py # 保存先パス生成
│   └── logger.py        # ログ設定・自動クリーンアップ
└── downloader/
    ├── base.py          # BaseDownloader（共通ライフサイクル）
    ├── rakuten.py       # 楽天市場
    ├── yahoo.py         # Yahoo Shopping
    ├── amazon.py        # Amazon Seller Central
    └── next_engine.py   # ネクストエンジン（Cookie バナー対応）

data/
├── cookies/             # Cookie / storage_state JSON
│   ├── rakuten_*.json
│   ├── yahoo.json
│   └── next_engine.json
└── amazon_profile/      # Amazon persistent browser profile

logs/
├── YYYY-MM-DD.log       # 日次ログ
└── screenshots/         # エラー時スクリーンショット
```

## 処理フロー

### メインループ（main.py）

```
1. CLI 引数パース → AppConfig 生成
2. target_dates 決定（--date or --date-from/--date-to）
3. サイトごとにループ（外側）:
   a. ブラウザコンテキスト作成（Cookie復元）
   b. ログイン（1回のみ、Cookie有効ならスキップ）
   c. 日付ごとにループ（内側）:
      - config.target_date を差し替え
      - download() 実行
      - 結果を記録（成功/失敗は日付単位）
   d. Cookie 保存
   e. コンテキスト終了
4. 日付×サイト別の結果サマリー出力
```

### BaseDownloader ライフサイクル

```python
async def run_multi_dates(dates: list[date]) -> dict[str, DownloadResult]:
    """1セッションで複数日付をダウンロード"""
    page = new_page()
    try:
        login()                    # 1回のみ
        for target_date in dates:
            config.target_date = target_date
            files = download()     # 各サブクラスが実装
            results[date] = OK/NG
    finally:
        save_cookies()
        page.close()
```

### 各ダウンローダーの特記事項

| サイト | Cookie スキップ判定 | DL 特記事項 | データ0件判定 |
|--------|---------------------|-------------|--------------|
| 楽天 | password 入力が見えたら ID スキップ | 「認証が必要です」最大3回リトライ、CSV作成→DLリンク待機→認証ダイアログ | 「データ件数は0件です」→ 空リスト |
| Yahoo | `input[name="handle"]` 不可視 → 全スキップ | 詳細検索タブ → 出荷日設定 → 注文DL画面 → 注文/商品 2ファイル | 「該当する注文がありません」→ 空リスト |
| Amazon | persistent_context で 2FA 記憶 | 全注文: kat-dropdown(value="7") + 処理中ポーリング。トランザクション: kat-date-picker + CustomEvent(isoValue) | トランザクション「結果が見つかりませんでした」→ スキップ |
| NE | `#user_login_code` 不可視 → スキップ。Cookie 同意バナー自動閉じ | 受注一覧 → 詳細検索 → DL → 全選択 → 明細一覧 → 伝票明細 → 別タブDL | 「結果はありませんでした」→ スキップ |

## CLI 使用例

```bash
# デフォルト（前日・全サイト・ヘッドレス）
uv run python -m src.main

# 特定日付
uv run python -m src.main --date 2026-03-10

# 日付範囲（各日付を個別にDL）
uv run python -m src.main --date-from 2026-03-09 --date-to 2026-03-11

# 特定サイトのみ
uv run python -m src.main --site rakuten,yahoo

# ブラウザ表示モード
uv run python -m src.main --no-headless

# 組み合わせ
uv run python -m src.main --date-from 2026-03-09 --date-to 2026-03-11 --site amazon --no-headless
```

## テスト結果

### 複数日付テスト（2026-03-10, 2026-03-11 / --no-headless）

| サイト | 3/10 | 3/11 | ログイン |
|--------|------|------|---------|
| 楽天 | ✅ 35.6秒 | ✅ 19.2秒 | 1回（認証リトライ1回） |
| Yahoo | ✅ 8.8秒 | ✅ 8.0秒 | スキップ（Cookie） |
| Amazon | ✅ 35.6秒 | ✅ 62.8秒 | 1回 |
| NE | ✅ 45.8秒 | ✅ 38.4秒 | スキップ（Cookie） |
| **合計** | | | **8成功 / 0失敗 / 294.3秒** |

### ヘッドレス安定性テスト（2026-03-13〜15 / 3日分・全サイト）

| サイト | 3/13 | 3/14 | 3/15 |
|--------|------|------|------|
| 楽天 | ✅ 1ファイル | ✅ 0件スキップ | ✅ 0件スキップ |
| Yahoo | ✅ 2ファイル | ✅ 0件スキップ | ✅ 0件スキップ |
| Amazon | ✅ 2ファイル | ✅ 2ファイル | ✅ 1ファイル (トランザクション0件) |
| NE | ✅ 2ファイル | ✅ 0件スキップ | ✅ 0件スキップ |
| **合計** | | | **12成功 / 0失敗 / 331.4秒** |

### タスクスケジューラからの実行テスト（2026-03-16 / 3/15分）

| サイト | 結果 | 備考 |
|--------|------|------|
| 楽天 | ✅ | 0件スキップ |
| Yahoo | ✅ | 0件スキップ |
| Amazon | ✅ | AllOrderReport_20260315.txt 保存 |
| NE | ✅ (修正後) | 初回: Cookie バナーでクリック妨害 → `_dismiss_cookie_banner()` 追加後に成功 |

## 未解決事項

| # | 内容 | 優先度 |
|---|------|--------|
| 1 | 1週間の本番試行 → 安定性確認 | 中 — タスクスケジューラで自動運用中 |
