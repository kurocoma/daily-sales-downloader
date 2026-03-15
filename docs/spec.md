# 要件定義書 — 日別売上集計データ自動ダウンロード

## 1. 概要

EC モール（楽天・Yahoo・Amazon）およびネクストエンジンから、日次の受注データを
Playwright ヘッドレスブラウザで自動ダウンロードするツール。

## 2. 目的

1. 1日1回行う各サイトの受注データダウンロードを **完全自動化** する
2. エラー発生時に **過不足なく再ダウンロード** できる仕組みを作る
3. 深夜の自動実行でエラーリスクを最小化し、発生時のリカバリーを確実にする
4. ID・PW は `docs/ID・PW.xlsx` に格納し、**git には絶対にアップしない**

## 3. 対象モール・ダウンロードデータ

| # | モール | データ種別 | ファイル形式 |
|---|--------|-----------|-------------|
| 1 | 楽天市場 | 日別売上データ（全カラム） | CSV |
| 2 | Yahoo Shopping | 注文データ（出庫管理用_ver2） | CSV |
| 3 | Yahoo Shopping | 商品データ（出庫管理用_ver2） | CSV |
| 4 | Amazon | 全注文レポート | TSV |
| 5 | Amazon | 日別トランザクション | CSV |
| 6 | ネクストエンジン | 購入者データ | CSV |
| 7 | ネクストエンジン | 商品情報データ | CSV |

## 4. ダウンロード保存先

ベースパス: `C:\Users\{USERNAME}\{会社共有フォルダ}\日別売上集計\{YYYY}\`

| モール | サブパス | 例 (2026年3月) |
|--------|---------|----------------|
| 楽天 | `楽天\日別売上データ\{M}月\` | `...\2026\楽天\日別売上データ\3月\` |
| Yahoo (商品) | `yahoo\item\{M}月\` | `...\2026\yahoo\item\3月\` |
| Yahoo (注文) | `yahoo\order\{M}月\` | `...\2026\yahoo\order\3月\` |
| Amazon (全注文) | `amazon\全注文レポート\{M}月\` | `...\2026\amazon\全注文レポート\3月\` |
| Amazon (トランザクション) | `amazon\日別トランザクション\{M}月\` | `...\2026\amazon\日別トランザクション\3月\` |
| NE (購入者) | `ネクストエンジン\購入者データ\` | `...\2026\ネクストエンジン\購入者データ\` |
| NE (商品情報) | `ネクストエンジン\商品情報データ\` | `...\2026\ネクストエンジン\商品情報データ\` |

### ルール
- 年・月ごとにディレクトリが変わる（ネクストエンジンは月別なし）
- `{USERNAME}` は環境変数から取得

### ファイル名フォーマット

| モール | パターン | 例 |
|--------|---------|-----|
| 楽天 | `YYYYMMDD.csv` | `20260311.csv` |
| Yahoo (注文) | `YYYYMMDD_order.csv` | `20260311_order.csv` |
| Yahoo (商品) | `YYYYMMDD_item.csv` | `20260311_item.csv` |
| Amazon (全注文) | `AllOrderReport_YYYYMMDD.txt` | `AllOrderReport_20260311.txt` |
| Amazon (トランザクション) | `YYYYMMDD_YYYYMMDDの期間の取引.csv` | `20260311_20260311の期間の取引.csv` |
| NE (購入者) | `YYYYMMDD.csv` | `20260311.csv` |
| NE (商品情報) | `YYYYMMDD.csv` | `20260311.csv` |

## 5. 各モールのダウンロード手順・セレクタ

### 5.1 楽天市場

**ログインURL**: `https://glogin.rms.rakuten.co.jp/?module=BizAuth&action=BizAuthCustomerAttest&sp_id=1`

| ステップ | 操作 | セレクタ |
|---------|------|---------|
| 1 | 1画面目 — R-Login ID入力 | `input#rlogin-username-ja[name="login_id"]` |
| 1b | 1画面目 — R-Login パスワード入力 | `input#rlogin-password-ja[name="passwd"]` |
| 1c | 1画面目 — 「楽天会員ログインへ」クリック | `button.rf-button-primary[name="submit"]` |
| 2 | 2画面目 — 楽天会員パスワード入力 | `input#password_current[name="password"]` |
| 2b | 2画面目 — 「次へ」クリック | `div#cta011[role="button"]` |
| 3 | 3画面目 — 「次へ」クリック | `button.rf-button-primary[name="submit"]` (テキスト: 次へ) |
| 4 | 4画面目 — RMS利用確認 | `button.btn-reset.btn-round.btn-red[type="submit"]` |
| 5 | CSV DL ページへ遷移 | URL: `https://csvdl-rp.rms.rakuten.co.jp/rms/mall/csvdl/CD02_01_001?dataType=opp_order#result` |
| 6 | 期間指定 — 開始日 | `select[name="fromYmd"]` → 前日の値を選択 |
| 6b | 期間指定 — 終了日 | `select[name="toYmd"]` → 前日の値を選択 |
| 7 | 発送日ラジオボタン選択 | `input#r06[name="dateType"][value="4"]` |
| 8 | 出力テンプレート → 全カラムダウンロード用 | `select[name="templateId"]` → `value="-1"` |
| 9 | 「データを作成する」クリック | `input#dataCreateBtn` |

### 5.2 Yahoo Shopping

**ログインURL**: `https://pro.store.yahoo.co.jp/pro.{STORE_ID}`
→ Yahoo ログイン画面にリダイレクト

| ステップ | 操作 | セレクタ |
|---------|------|---------|
| 1 | 1画面目 — ID入力 | `input.riff-FormElement__input[name="handle"]` (placeholder: 携帯電話番号/メールアドレス/ID) |
| 1b | 1画面目 — 「次へ」クリック | `button.riff-Clickable__root` (テキスト: 次へ) |
| 2 | 2画面目 — パスワード入力 | `input.riff-FormElement__input[name="password"]` |
| 2b | 2画面目 — 「ログイン」クリック | `button.riff-Clickable__root` (テキスト: ログイン) |
| 3 | ストア管理ページへ遷移 | URL: `https://pro.store.yahoo.co.jp/pro.{STORE_ID}` |
| 4 | 注文管理画面へ移動 | URL: `https://pro.store.yahoo.co.jp/pro.{STORE_ID}/order/manage/index` |
| 5 | 詳細検索タブ切替 | `ul#tab a[href="#tab02"]` をクリック |
| 6 | 出荷日 — 開始 | `input#ShipDateFrom[name="ShipDateFrom"]` |
| 6b | 出荷日 — 終了 | `input#ShipDateTo[name="ShipDateTo"]` |
| 7 | 「注文データダウンロード」クリック | `a[onclick="openSelectDownloadFilePage('index');"]` |
| 8 | 出庫管理用_ver2（注文データ）DL | `fileDownload` の `onclick` リンク（注文データ行） |
| 9 | 出庫管理用_ver2（商品データ）DL | `fileDownload` の `onclick` リンク（商品データ行） |

### 5.3 Amazon — 全注文レポート

**ログイン**: Amazon Seller Central（2FA あり）
- 初回は手動ログイン → Cookie を `data/cookies/amazon.json` に保存
- 以降は Cookie で自動ログイン。2FA 失効時は通知して手動対応

**DLページ**: `https://sellercentral.amazon.co.jp/reportcentral/FlatFileAllOrdersReport/1`

| ステップ | 操作 | セレクタ |
|---------|------|---------|
| 1 | レポートのタイプ: 注文日 | `kat-radiobutton[value="2400"]` (デフォルト checked) |
| 2 | レポート期間: 前日 | `kat-dropdown` → `value="1"` (前日) |
| 3 | 「ダウンロードのリクエスト」クリック | `kat-button[label="ダウンロードのリクエスト"]` |
| 4 | 「処理中」→「ダウンロード」待機 | `kat-button[label="キャンセル"]` が消え、`kat-button[label="ダウンロード"]` が出現するまでポーリング |
| 5 | 「ダウンロード」ボタンクリック | `kat-button[label="ダウンロード"]` (variant="secondary", size="small") |

### 5.4 Amazon — 日別トランザクション

**DLページ**: `https://sellercentral.amazon.co.jp/payments/event/view?resultsPerPage=10&pageNumber=1`

| ステップ | 操作 | セレクタ |
|---------|------|---------|
| 1 | 開始日を設定 | `kat-date-picker[name="startDate"]` |
| 2 | 終了日を設定 | `kat-date-picker[name="endDate"]` |
| 3 | 「更新」ボタン押下 | `kat-button[label="更新"].filter-update-button` |
| 4 | 「ダウンロード」ボタン出現待機 → クリック | `kat-button.download-button[label="ダウンロード"]` |

### 5.5 ネクストエンジン

**ログインURL**: `https://base.next-engine.org/users/sign_in/`

| ステップ | 操作 | セレクタ |
|---------|------|---------|
| 1 | ネクストエンジンID入力 | `input#user_login_code[name="user[login_code]"]` |
| 1b | パスワード入力 | `input#user_password[name="user[password]"]` |
| 1c | ワンタイムパスワード | スキップ（不要） |
| 1d | 「ログイン」クリック | `input[name="commit"][value="ログイン"]` |
| 2 | （不定期）お知らせ → 「すべて既読にする」 | `button.markasread[data-newsonly="1"]` → OKポップアップ accept |
| 3 | 受注一覧へ遷移 | URL: `https://main.next-engine.com/Userjyuchu/index?search_condi=17` |
| 4 | 「詳細検索」クリック | `button#jyuchu_dlg_open` |
| 5 | ミニウィンドウ — 「クリア」押下 | `input[value="　　クリア　　"][onclick="searchJyuchu.clear()"]` |
| 6 | 受注キャンセル区分 → 0 | `select` で `option[value="0"]` (name=`sea_jyuchu_search_field49_id`) |
| 7 | 出荷確定日 — 開始 | `input#sea_jyuchu_search_field36_from` |
| 7b | 出荷確定日 — 終了 | `input#sea_jyuchu_search_field36_to` |
| 8 | 「検索」押下 | ミニウィンドウ内の検索ボタン（ダイアログ `#ne_dlg_searchJyuchuDlg` 内） |
| 9 | テーブル表示待機 → 「ダウンロード」クリック | `a#searchJyuchu_table_dl_lnk` |
| 10 | 「全て選択」クリック | `button#all_check` |
| 11 | 「明細一覧」クリック | `img[alt="明細一覧"]` |
| 12 | モーダル — 「伝票明細単位で出力」選択 | `span` テキスト "伝票明細単位で出力" をクリック |
| 13 | 「開く」ボタン押下 | `button#btn_meisai_exec` |
| 14 | 別タブで「ダウンロード」クリック | 新タブの `a#searchJyuchu_table_dl_lnk` |

## 6. Cookie 対応ログイン（全サイト共通）

各サイトでログインセッション（Cookie / storage_state）を保存・復元し、
認証済みの場合はログイン処理をスキップする。

| サイト | 保存形式 | 保存先 | スキップ判定 |
|--------|---------|--------|-------------|
| 楽天 | storage_state JSON × 3 | `data/cookies/rakuten_*.json` | `input[type="password"]` の可視判定で ID 入力スキップ |
| Yahoo | storage_state JSON | `data/cookies/yahoo.json` | `input[name="handle"]` が不可視ならログイン全スキップ |
| Amazon | persistent_context (UserDataDir) | `data/amazon_profile/` | 2FA デバイス記憶。Cookie 失効時は手動対応 |
| NE | storage_state JSON | `data/cookies/next_engine.json` | `#user_login_code` が不可視ならログイン全スキップ → 「メイン機能」クリックのみ |

### 楽天 — 認証エラーリトライ

楽天はログイン成功後でも CSV DL ページで「認証が必要です」が表示されることがある。
最大3回まで再ログイン→CSV DL ページ再アクセスをリトライする。

## 7. Amazon Shadow DOM 操作

### 7.1 全注文レポート — kat-dropdown

`kat-dropdown.daily-time-picker-kat-dropdown-normal` に `value="7"`（過去7日間）を
JavaScript で直接設定し、`CustomEvent('change')` を発火。

レポートリクエスト後は「処理中」テキストをポーリング（最大30回 × 10秒）し、
「ダウンロード」ボタンが出現するまで待機。ページリロード＋オーバーレイ除去を併用。

### 7.2 日別トランザクション — kat-date-picker

`kat-date-picker[name="startDate"]` / `kat-date-picker[name="endDate"]` に対して
`picker.value` を直接設定し、`CustomEvent('change', { detail: { isoValue, value } })`
を発火。startDate → endDate の順に 1 秒間隔で設定する。

## 8. 複数日付サポート

### 概要

ネットワークエラーやPC停止からのリカバリーのため、複数の日付を一度に指定して
各日付を **1日ずつ個別に** 全サイトからダウンロードできる。

### CLI 引数

| 引数 | 説明 | デフォルト |
|------|------|-----------|
| `--date YYYY-MM-DD` | 単一日付を指定 | 前日 |
| `--date-from YYYY-MM-DD` | 開始日（`--date-to` と併用） | — |
| `--date-to YYYY-MM-DD` | 終了日（`--date-from` と併用） | — |
| `--site site1,site2` | 対象サイト（カンマ区切り） | 全サイト |
| `--no-headless` | ブラウザ表示モード | ヘッドレス |

### 処理フロー（サイトループ → 日付ループ）

画面遷移を最小化するため、**サイト単位でログインし、同一セッション内で日付を切り替えてDL** する。

```
楽天: ログイン(1回) → DL(3/9) → DL(3/10) → DL(3/11) → Cookie保存 → close
Yahoo: ログイン(1回) → DL(3/9) → DL(3/10) → DL(3/11) → Cookie保存 → close
Amazon: ログイン(1回) → DL(3/9) → DL(3/10) → DL(3/11) → close
NE:    ログイン(1回) → DL(3/9) → DL(3/10) → DL(3/11) → Cookie保存 → close
```

日付ごとにエラーは個別に記録され、1日分が失敗しても他の日付は継続する。

## 9. データ0件ハンドリング

対象日にデータ（出荷・注文・トランザクション）が存在しない場合、タイムアウトエラーにせず
「データ0件 — スキップ」として正常終了（成功扱い・ファイル0件）する。

| サイト | 判定テキスト | 判定タイミング |
|--------|------------|--------------|
| 楽天 | 「この条件でのデータ件数は0件です」 | 「データを作成する」クリック後 |
| Yahoo | 「該当する注文がありません」 | 注文データダウンロード画面遷移後 |
| Amazon (トランザクション) | 「結果が見つかりませんでした」 | 「更新」ボタン押下後 |
| NE (購入者/商品情報) | 「結果はありませんでした」 | 詳細検索実行後 |

**注**: Amazon 全注文レポートは「過去7日間」指定のため、通常は0件にならない。

## 10. ログ・エラーハンドリング

### ログファイル

| 項目 | 内容 |
|------|------|
| 出力先 | `logs/YYYY-MM-DD.log` |
| レベル | コンソール: INFO / ファイル: DEBUG |
| 自動クリーンアップ | 30日以上前のログ・スクリーンショットを起動時に削除 |

### ログ内容

- **起動時**: Python バージョン、プラットフォーム、Playwright バージョン
- **各サイト**: ログイン結果、DL開始/完了、保存先パス、経過時間
- **エラー時**: エラーメッセージ、スタックトレース（DEBUG）、エラー時の URL・ページタイトル
- **完了時**: 日付×サイト別の成功/失敗サマリー、合計経過時間

### スクリーンショット

エラー時に `logs/screenshots/{site}_{timestamp}.png` へ自動保存。

## 11. 非機能要件

| 項目 | 内容 |
|------|------|
| 実行タイミング | 毎日深夜（Windows タスクスケジューラ） |
| リトライ | 楽天認証エラー: 最大3回リトライ |
| ログ | 日次ログファイル + コンソール出力 |
| 通知 | 不要（ログのみ） |
| リカバリー | `--date` / `--date-from` `--date-to` / `--site` 指定での再ダウンロード |
| セキュリティ | ID・PW は xlsx ファイルから読み取り。git 管理外 |
| 環境 | Windows 11, Python 3.13+ + Playwright, uv |
| Cookie管理 | 全サイトで Cookie/storage_state 保存・復元 |

## 12. 確認事項

| # | 項目 | 状態 |
|---|------|------|
| Q1 | 楽天ログイン画面の各セレクタ（1〜4画面目） | **解決済** |
| Q2 | 楽天 CSV DL 画面の発送日・テンプレート選択セレクタ | **解決済** |
| Q3 | Yahoo ログイン画面のセレクタ | **解決済** |
| Q4 | Yahoo 出荷日入力・DL ボタンのセレクタ | **解決済** |
| Q5 | Amazon 2FA の運用方法 | **解決済** — persistent_context + Cookie保存 |
| Q6 | Amazon 日別トランザクションの URL | **解決済** — `https://sellercentral.amazon.co.jp/payments/event/view` |
| Q7 | ネクストエンジン ログイン画面のセレクタ | **解決済** |
| Q8 | ネクストエンジン お知らせ既読・クリア・検索ボタンのセレクタ | **解決済** |
| Q9 | エラー通知の手段 | **解決済** — 不要（ログのみ） |
| Q10 | ファイル名の厳密なフォーマット | **解決済** — 上記「ファイル名フォーマット」セクション参照 |
| Q11 | ネクストエンジンは月別ディレクトリなし? | **解決済** — 月別なし（年直下に購入者データ/商品情報データ） |
| Q12 | 楽天「データを作成する」押下後の待機・DLフロー | **解決済** — 実装完了、DLリンク待機+認証ダイアログ自動入力 |
| Q13 | Amazon kat-dropdown / kat-date-picker の Shadow DOM 操作 | **解決済** — JavaScript 直接設定 + CustomEvent |
| Q14 | Cookie対応ログイン（全サイト） | **解決済** — セクション6参照 |
| Q15 | 複数日付のリカバリーダウンロード | **解決済** — セクション8参照 |
| Q16 | データ0件時のハンドリング | **解決済** — セクション9参照 |
