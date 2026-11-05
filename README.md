# 社内案件管理システム

営業案件（リード〜受注/失注）を管理する社内向け Web アプリです。Django + SQLite 構成。

## 機能

- **ログイン・ユーザー管理** — 社員アカウントでログイン。管理者はユーザーの追加・編集・無効化・パスワード再設定が可能
- **案件管理** — 一覧（キーワード/フェーズ/担当者/顧客/受注予定日で絞り込み、並び替え、CSV出力）、登録・編集・削除
- **活動履歴** — 案件ごとのコメント（商談メモ）と、作成・項目変更の自動記録（「フェーズ: 提案 → 受注」のように旧→新を表示）
- **顧客管理** — 顧客の登録・編集、顧客ごとの案件一覧
- **ダッシュボード** — 直近12か月の月別受注額グラフ（ホバーで詳細、表表示あり）、進行中件数、パイプライン総額、加重見込み（金額×確度）、今月の受注額・受注率、フェーズ別集計、期限切れ案件、30日以内の受注予定、自分の担当案件

### フェーズ

リード → 提案 → 見積 → 交渉 → 受注 / 失注
「受注」「失注」にすると確度（100% / 0%）とクローズ日が自動設定されます。

### 権限

| 操作 | 一般ユーザー | 管理者 (is_staff) |
|---|---|---|
| 案件・顧客の閲覧/登録/編集 | ○ | ○ |
| 案件の削除 | 自分が担当者/作成者の案件のみ | ○ |
| 顧客の削除（案件なしの顧客のみ） | × | ○ |
| コメントの削除 | 自分のコメントのみ | ○ |
| ユーザー管理 | × | ○ |

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

`admin / admin12345`（管理者）、`sato`・`suzuki`・`tanaka / demo12345`（一般）と、顧客8社・案件60件（過去1年分の受注/失注を含む）を作成します。`--reset` を付けると既存の案件・顧客を消してから作り直します。**本番環境では実行しないでください。**

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
deals/       顧客・案件モデル、ダッシュボード、一覧/検索/CSV
templates/   画面テンプレート
static/css/  スタイル（ライト/ダークモード対応）
deploy/gcp/  Google Cloud 構築・デプロイスクリプト
docs/        運用ドキュメント
```
