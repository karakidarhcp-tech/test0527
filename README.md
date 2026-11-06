# 社内案件管理システム

営業案件（リード〜受注/失注）を管理する社内向け Web アプリです。Django + SQLite 構成。

## 機能

案件番号で **案件 → 見積 → 受注 → 分割請求 → 請求書 → 入金** がひと続きにつながる、特注家具・内装向けの業務アプリです。

| 画面 | できること |
|---|---|
| 案件 | 案件番号の自動採番（`2611001` = 26年11月の1件目）、追加工事（`2611001-A1`）、確定金額・計上月・工期・現場住所、活動履歴 |
| 見積 | 版管理（`-Q1`, `-Q2`…、複製して改訂）、明細編集（品目マスタから追加・合計の自動計算）、**原価積算**（材料の拾い出し＋見込製作時間×労務単価＋外注費 → 目標粗利率で単価を提案）、粗利の確認、PDF 発行 |
| 受注 | 見積から確定金額を設定し、着工金・中間金・残金の **分割請求予定** を自動作成（割合は会社設定） |
| 請求・入金 | 予定から請求書（`-B1`, `-B2`…）を作成（一括1行 or 見積明細を引き継ぎ）、支払期限は顧客の締め日・支払条件から自動計算、PDF 発行、入金登録（一部入金・手数料差引に対応）、請求待ち／未入金／期限超過の一覧 |
| 品目・原価 | 品目マスタ、**Excel（.xlsx）/ CSV の原価表を取り込み**（列名の揺れに対応、テンプレートあり） |
| 書類控え | 発行した見積書・請求書の PDF 原本を保存（変更・削除不可）。日付・金額・取引先で検索 |
| ダッシュボード | パイプライン、月別受注額、期限切れ案件など |
| 設定 | 会社情報・登録番号・振込先・労務単価・目標粗利率・分割請求の割合、ユーザー管理 |

- 消費税は **インボイス制度** に合わせ、書類ごと・税率ごとに 1 回だけ端数処理（切り捨て）
- 発行済みの見積は編集不可（修正は新しい版）。発行済みの請求書は管理者のみ理由を付けて下書きに戻せる（旧 PDF は控えに残る）
- PC・iPhone・iPad のブラウザに対応
- 業務ルール・番号ルールの詳細は [CLAUDE.md](CLAUDE.md)

### 権限

| 操作 | 一般ユーザー | 管理者 (is_staff) |
|---|---|---|
| 案件・見積・請求・入金の登録/編集 | ○ | ○ |
| 案件の削除 | 自分が担当者/作成者の案件のみ | ○ |
| 発行済み請求書を下書きに戻す | × | ○ |
| 顧客の削除・会社設定・ユーザー管理 | × | ○ |

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # 最初の管理者を作成
python manage.py runserver
```

http://127.0.0.1:8000/ にアクセスしてログインします。

### デモデータ（開発用）

```bash
python manage.py seed_demo
```

`admin / admin12345`（管理者）、`sato`・`suzuki`・`tanaka / demo12345`（一般）と、デモの会社設定・品目マスタ・顧客・案件・見積・請求書・入金を作成します。`--reset` を付けると既存の業務データを消してから作り直します。**本番環境では実行しないでください。**

### テスト

```bash
python manage.py test
```

## Google Cloud へのデプロイ

Cloud Run + Cloud SQL (PostgreSQL) で公開する手順を **[docs/deploy-gcp.md](docs/deploy-gcp.md)** にまとめています。
ブラウザ（Cloud Shell）だけで、次の2コマンドで構築・公開できます。

```bash
./deploy/gcp/setup.sh    # 初回のみ: DB・シークレット・権限などを作成
./deploy/gcp/deploy.sh   # 毎回: ビルド → DBマイグレーション → 公開
```

## 本番運用時の設定

環境変数で設定します。

| 変数 | 説明 |
|---|---|
| `DJANGO_SECRET_KEY` | 必須。ランダムな長い文字列 |
| `DJANGO_DEBUG` | `0` にする |
| `DJANGO_ALLOWED_HOSTS` | 公開するホスト名（カンマ区切り） |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 公開するURL（例: `https://anken.example.co.jp`） |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | 設定すると PostgreSQL を使用（未設定なら SQLite） |

`Dockerfile` で本番用コンテナ（gunicorn + WhiteNoise による静的ファイル配信）を作成できます。死活監視用に `/healthz` を用意しています。

Django 標準の管理画面は `/admin/` で利用できます（スーパーユーザーのみ）。

## 構成

```
config/      プロジェクト設定・URL
accounts/    ログイン、ユーザー管理、プロフィール
deals/       顧客・案件・採番（numbering.py）、ダッシュボード
catalog/     品目・原価マスタ、Excel 取り込み、会社設定、金額・税計算（pricing.py）
quotes/      見積・明細・原価積算
billing/     受注・分割請求・請求書・入金、支払期限の計算（terms.py）
documents/   PDF 生成と発行済み書類の保存・検索
templates/   画面テンプレート
static/css/  スタイル（ライト/ダークモード対応）
deploy/gcp/  Google Cloud 構築・デプロイスクリプト
docs/        運用ドキュメント
```
