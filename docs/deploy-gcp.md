# Google Cloud へのデプロイ手順

Googleアカウントで管理する Google Cloud 上に、案件管理システムを公開する手順です。
すべてブラウザだけ（Cloud Shell）で完結し、パソコンへのインストールは不要です。

## 構成

```
社員のブラウザ ──HTTPS──▶ Cloud Run（アプリ本体・自動でHTTPS）
                              │
                              ├─▶ Cloud SQL for PostgreSQL（データ・毎日自動バックアップ）
                              └─▶ Secret Manager（DBパスワード・秘密鍵）
```

| サービス | 役割 |
|---|---|
| Cloud Run | アプリを動かす。アクセスがない時は 0 台まで縮小し、課金も止まる |
| Cloud SQL | PostgreSQL データベース。毎日 3:00（日本時間）に自動バックアップ（14日分保持）、任意時点への復元にも対応 |
| Secret Manager | パスワード類をコードに書かずに安全に保管 |
| Cloud Build / Artifact Registry | コンテナイメージの作成と保管 |

### 費用の目安

- **Cloud SQL（db-f1-micro・10GB・バックアップ込み）: 月 2,000〜3,000 円程度**（費用の大半はこれ。起動している間は常に課金）
- Cloud Run・Cloud Build・Secret Manager: 社内利用規模なら無料枠内に収まることが多い

正確な金額は [料金計算ツール](https://cloud.google.com/products/calculator) で確認してください。
想定外の請求を防ぐため、手順 1 で **予算アラート** の設定をおすすめします。

---

## 初回セットアップ

### 1. Google Cloud プロジェクトを用意する（ブラウザ操作）

1. Googleアカウントで <https://console.cloud.google.com/> にログイン
2. 画面上部のプロジェクト選択 →「新しいプロジェクト」→ 名前（例: `anken-system`）を付けて作成
3. 左メニュー「お支払い」で請求先アカウントをリンク（クレジットカード登録。初回は無料トライアルあり）
4. （推奨）「お支払い」→「予算とアラート」で月 5,000 円などの予算アラートを作成
5. 作成したプロジェクトの **プロジェクトID** を控える（例: `anken-system-123456`。名前とは別物なので注意）

### 2. Cloud Shell を開く

コンソール右上の **「>_」アイコン（Cloud Shell をアクティブにする）** をクリック。
画面下にターミナルが開きます。gcloud・git・Python はすべて入っており、ログインも済んだ状態です。

### 3. ソースコードを取得する

```bash
git clone https://github.com/karakidarhcp-tech/test0527.git anken
cd anken
git checkout claude/deal-management-mvp   # main にマージ済みなら不要
```

> リポジトリが非公開の場合、ユーザー名と **パスワードの代わりに GitHub の Personal Access Token** を求められます。
> GitHub の Settings → Developer settings → Personal access tokens で、このリポジトリの読み取り権限を持つトークンを発行してください。

### 4. 設定ファイルを作る

```bash
cp deploy/gcp/config.env.example deploy/gcp/config.env
nano deploy/gcp/config.env      # PROJECT_ID= を手順1で控えたIDに書き換え、Ctrl+O → Enter → Ctrl+X で保存
```

### 5. 環境を構築する（初回のみ・10〜15分）

```bash
./deploy/gcp/setup.sh
```

最後に **初期管理者のパスワード** が表示されるので控えてください。

### 6. デプロイする（5分前後）

```bash
./deploy/gcp/deploy.sh
```

最後に表示される `https://anken-xxxxxxxx.asia-northeast1.run.app` が社員に共有するURLです。

### 7. 初期設定（ブラウザ操作）

1. URL を開き、`admin` と手順5のパスワードでログイン
2. 右上の名前 →「パスワード変更」で自分だけが知るパスワードに変更
3. 「ユーザー管理」から社員のアカウントを作成（自分用の管理者アカウントも作り、`admin` は予備にするのがおすすめ）

---

## 更新のしかた（機能追加・修正のたび）

Cloud Shell で:

```bash
cd ~/anken
git pull
./deploy/gcp/deploy.sh
```

データベースの変更（マイグレーション）もこのスクリプトが自動で適用します。

## よく使う操作

| やりたいこと | 方法 |
|---|---|
| アプリのログ・エラーを見る | コンソール → Cloud Run → `anken` →「ログ」タブ |
| バックアップを確認・復元 | コンソール → SQL → `anken-db` →「バックアップ」 |
| 前のバージョンに戻す | コンソール → Cloud Run → `anken` →「リビジョン」→ 戻したい版に「トラフィックを管理」で 100% |
| 管理者パスワードを再確認 | `gcloud secrets versions access latest --secret=anken-admin-password`（初期値のみ。変更後のものは確認不可） |

## さらに安全にする（任意）

### 会社の Google アカウントを持つ人だけがアクセスできるようにする

今の構成では、URL を知っていれば誰でもログイン画面までは表示できます（ログインしないと何も見られません）。
Google Workspace を使っている会社なら、**Identity-Aware Proxy (IAP)** を Cloud Run に設定すると、
会社の Google アカウントでログインした人しかログイン画面にすら到達できなくなります。
設定方法: <https://cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run>

### 独自ドメイン（例: `anken.example.co.jp`）

`config.env` の `CUSTOM_DOMAIN` を設定して `deploy.sh` を実行後、
コンソール → Cloud Run →「カスタム ドメインを管理」でドメインを割り当て、DNS を設定します。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `setup.sh` で `PERMISSION_DENIED` | プロジェクトの「オーナー」権限があるアカウントで実行しているか、課金が有効か確認 |
| `deploy.sh` のビルドで権限エラー | 組織ポリシーで Cloud Build の既定権限が制限されている場合があります。IAM で Cloud Build が使うサービスアカウント（`<プロジェクト番号>-compute@developer.gserviceaccount.com`）に「Artifact Registry 書き込み」「ログ書き込み」ロールを付与 |
| 画面に `Bad Request (400)` | アクセスしたURLが許可リストにない。`deploy.sh` を再実行（表示された URL を自動で許可します） |
| ログイン時に `CSRF 検証に失敗` | 上と同じく `deploy.sh` を再実行。独自ドメインなら `CUSTOM_DOMAIN` を設定 |
| 初回アクセスが遅い | アクセスがない時は 0 台に縮小するため、最初の 1 回は数秒かかります。気になる場合は `deploy.sh` の `--min-instances=0` を `1` に（月 1,000〜2,000 円程度増） |

## 全部削除したいとき

費用を完全に止めるには、コンソール →「IAM と管理」→「設定」→ **プロジェクトをシャットダウン**。
（Cloud SQL には削除保護が付いているため、個別に消す場合は先に保護を解除してください）
