#!/usr/bin/env bash
# 初回だけ実行する Google Cloud の環境構築スクリプト（何度実行しても安全）
#   - 必要な API の有効化
#   - Cloud SQL (PostgreSQL) の作成、DB・ユーザー作成、自動バックアップ設定
#   - Secret Manager に秘密情報を保存
#   - Cloud Run 用サービスアカウントと権限
#   - コンテナイメージの保存先 (Artifact Registry)
source "$(dirname "$0")/common.sh"

random_secret() { python3 -c "import secrets; print(secrets.token_urlsafe(${1:-32}))"; }

create_secret_if_missing() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    echo "  シークレット $name は作成済み"
    return 1
  fi
  printf '%s' "$value" | gcloud secrets create "$name" --replication-policy=automatic --data-file=- >/dev/null
  echo "  シークレット $name を作成"
}

step "API を有効化（初回は数分かかります）"
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com

step "Artifact Registry（イメージ保存先）"
if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" --repository-format=docker --location="$REGION" \
    --description="案件管理システムのコンテナイメージ"
else
  echo "  作成済み"
fi

step "Cloud SQL インスタンス $SQL_INSTANCE（初回は 5〜10 分かかります）"
if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  # バックアップ開始 18:00 UTC = 日本時間 3:00。削除保護あり。
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_16 --edition=enterprise --tier="$SQL_TIER" \
    --region="$REGION" --storage-size=10 --availability-type=zonal \
    --backup-start-time=18:00 --retained-backups-count=14 \
    --enable-point-in-time-recovery --deletion-protection
else
  echo "  作成済み"
fi

step "データベース $DB_NAME"
if ! gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null 2>&1; then
  gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"
else
  echo "  作成済み"
fi

step "シークレット"
DB_PASSWORD="$(random_secret 24)"
if create_secret_if_missing "${SERVICE}-db-password" "$DB_PASSWORD"; then
  # 新しく作ったパスワードで DB ユーザーを作成（既存なら更新）
  if gcloud sql users list --instance="$SQL_INSTANCE" --format="value(name)" | grep -qx "$DB_USER"; then
    gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD"
  else
    gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD"
  fi
fi
create_secret_if_missing "${SERVICE}-django-secret-key" "$(random_secret 50)" || true
ADMIN_PASSWORD="$(random_secret 12)"
if create_secret_if_missing "${SERVICE}-admin-password" "$ADMIN_PASSWORD"; then
  NEW_ADMIN_PASSWORD="$ADMIN_PASSWORD"
fi

step "Cloud Run 用サービスアカウント"
if ! gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE}-run" --display-name="案件管理 Cloud Run"
  sleep 5  # 作成直後は権限付与が失敗することがあるため少し待つ
else
  echo "  作成済み"
fi
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" --role="roles/cloudsql.client" --condition=None >/dev/null
for s in db-password django-secret-key admin-password; do
  gcloud secrets add-iam-policy-binding "${SERVICE}-$s" \
    --member="serviceAccount:$RUN_SA" --role="roles/secretmanager.secretAccessor" >/dev/null
done
echo "  Cloud SQL 接続権限とシークレット読み取り権限を付与"

echo
echo "========================================================"
echo " 環境構築が完了しました。次は  ./deploy/gcp/deploy.sh  を実行してください。"
if [[ -n "${NEW_ADMIN_PASSWORD:-}" ]]; then
  echo
  echo " 初期管理者  ユーザー名: $ADMIN_USERNAME"
  echo "             パスワード: $NEW_ADMIN_PASSWORD"
  echo " ※ この表示は一度きりです。ログイン後、画面右上の名前→パスワード変更 で変更してください。"
  echo "   （再確認: gcloud secrets versions access latest --secret=${SERVICE}-admin-password）"
fi
echo "========================================================"
