# setup.sh / deploy.sh 共通の読み込み処理
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$SCRIPT_DIR/config.env"

if [[ ! -f "$CONFIG" ]]; then
  echo "設定ファイルがありません: $CONFIG"
  echo "  cp deploy/gcp/config.env.example deploy/gcp/config.env  を実行して PROJECT_ID を設定してください"
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG"

if [[ -z "${PROJECT_ID:-}" || "$PROJECT_ID" == "your-project-id" ]]; then
  echo "config.env の PROJECT_ID を自分のプロジェクトIDに書き換えてください"
  exit 1
fi

gcloud config set project "$PROJECT_ID" --quiet >/dev/null

INSTANCE_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
RUN_SA="${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com"
AR_REPO="${SERVICE}"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/app"

step() { echo; echo "==> $*"; }
