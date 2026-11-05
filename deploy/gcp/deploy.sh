#!/usr/bin/env bash
# アプリを Cloud Run にデプロイする（更新のたびに実行）
#   1. Cloud Build でコンテナイメージを作成
#   2. Cloud Run ジョブで DB マイグレーション（＋初回のみ管理者作成）
#   3. Cloud Run サービスを新しいイメージで更新
source "$(dirname "$0")/common.sh"

TAG="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
  TAG="${TAG}-dirty-$(date +%H%M%S)"
fi
IMAGE="${IMAGE_BASE}:${TAG}"

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUN_HOST="${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
HOSTS="$RUN_HOST"
ORIGINS="https://$RUN_HOST"
if [[ -n "${CUSTOM_DOMAIN:-}" ]]; then
  HOSTS="$HOSTS,$CUSTOM_DOMAIN"
  ORIGINS="$ORIGINS,https://$CUSTOM_DOMAIN"
fi

# 値にカンマを含むため区切り文字を @ に変更して渡す（gcloud の ^@^ 記法）
COMMON_ENV="^@^DJANGO_DEBUG=0@DB_NAME=${DB_NAME}@DB_USER=${DB_USER}@DB_HOST=/cloudsql/${INSTANCE_CONNECTION}"
SECRETS="DJANGO_SECRET_KEY=${SERVICE}-django-secret-key:latest,DB_PASSWORD=${SERVICE}-db-password:latest"

step "コンテナイメージをビルド: $IMAGE"
gcloud builds submit "$REPO_ROOT" --region="$REGION" --tag="$IMAGE"

step "DB マイグレーション（Cloud Run ジョブ ${SERVICE}-migrate）"
gcloud run jobs deploy "${SERVICE}-migrate" \
  --image="$IMAGE" --region="$REGION" --service-account="$RUN_SA" \
  --set-cloudsql-instances="$INSTANCE_CONNECTION" \
  --set-env-vars="${COMMON_ENV}@DJANGO_SUPERUSER_USERNAME=${ADMIN_USERNAME}" \
  --set-secrets="${SECRETS},DJANGO_SUPERUSER_PASSWORD=${SERVICE}-admin-password:latest" \
  --command=sh --args="-c,python manage.py migrate --noinput && python manage.py ensure_superuser" \
  --max-retries=0 --task-timeout=10m \
  --execute-now --wait

step "Cloud Run サービス $SERVICE を更新"
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" --region="$REGION" --service-account="$RUN_SA" \
  --add-cloudsql-instances="$INSTANCE_CONNECTION" \
  --set-env-vars="${COMMON_ENV}@DJANGO_ALLOWED_HOSTS=${HOSTS}@DJANGO_CSRF_TRUSTED_ORIGINS=${ORIGINS}" \
  --set-secrets="$SECRETS" \
  --allow-unauthenticated \
  --min-instances=0 --max-instances=3 --memory=512Mi --cpu=1 --concurrency=40

# Cloud Run は旧形式の URL（…-an.a.run.app）を返すことがある。その場合はそのホストも許可に追加
URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
if [[ "$URL" != "https://$RUN_HOST" ]]; then
  step "URL $URL もアクセス許可に追加"
  gcloud run services update "$SERVICE" --region="$REGION" \
    --update-env-vars="^@^DJANGO_ALLOWED_HOSTS=${HOSTS},${URL#https://}@DJANGO_CSRF_TRUSTED_ORIGINS=${ORIGINS},${URL}"
fi

echo
echo "========================================================"
echo " デプロイ完了: https://$RUN_HOST"
[[ "$URL" != "https://$RUN_HOST" ]] && echo "     （別名: $URL）"
echo "========================================================"
