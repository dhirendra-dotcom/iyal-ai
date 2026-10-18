#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Iyal.ai Lite - Deploy to Cloud Run
#
# Deploys ONE Cloud Run service:
#
#   /           -> site (landing page, mounted after all API routes)
#   /app/       -> frontend-lite
#   /api/...    -> FastAPI APIs
#   /chat       -> backend streaming
#
# Uses the DEFAULT Cloud Build service account.
# There is intentionally NO --build-service-account flag.
#
# Usage:
#   ./deploy-lite.sh PROJECT_ROOT ARTIFACT_BUCKET [RUNTIME_SERVICE_ACCOUNT]
#
# Example:
#   ./deploy-lite.sh \
#     ~/iyal-lite-work/current \
#     arthistics-artifacts \
#     arthistics-backend-sa@my-project.iam.gserviceaccount.com
#
# Required:
#   PROJECT_ROOT
#   ARTIFACT_BUCKET
#
# Optional environment overrides before running:
#   PROJECT_ID
#   REGION
#   SERVICE_NAME
#   GOOGLE_CLOUD_LOCATION
#
#   GEMINI_MODEL
#   GEMINI_SEGMENTATION_MODEL
#   GEMINI_TRANSCRIPTION_MODEL
#   GEMINI_IMAGE_MODEL
#
#
#   PRODUCT_SEARCH_ENABLED
#   PRODUCT_SEARCH_MODEL
#   PRODUCT_SEARCH_COUNTRY
#   PRODUCT_SEARCH_TOP_K
#   PRODUCT_SEARCH_TIMEOUT_SECONDS
#   PRODUCT_SEARCH_RETRY_UNPARSEABLE
#
#   MAX_UPLOAD_MB
#   MAX_TRANSCRIPTION_MB
#   SSE_HEARTBEAT_SECONDS
#   ARTHISTICS_LOG_LEVEL
#   ARTHISTICS_LOG_FORMAT
#
#   AGENT_PLATFORM_LOCATION
#   VERTEX_SESSION_RUNTIME_ID
#   VERTEX_MEMORY_BANK_ID
#   MEMORY_ENABLED
#   SESSION_DB_URL
#
#   SMTP_HOST
#   SMTP_PORT
#   SMTP_USERNAME
#   SMTP_PASSWORD
#   SMTP_USE_TLS
#   SUPPORT_EMAIL_FROM
#
# Cloud Run tuning:
#   MEMORY
#   CPU
#   TIMEOUT
#   MIN_INSTANCES
#   MAX_INSTANCES
#   CONCURRENCY
# ============================================================

PROJECT_ROOT="${1:-}"
GCS_BUCKET="${2:-}"
RUNTIME_SERVICE_ACCOUNT="${3:-}"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-iyalai}"

# Vertex/Gemini
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
AGENT_PLATFORM_LOCATION="${AGENT_PLATFORM_LOCATION:-$REGION}"
VERTEX_SESSION_RUNTIME_ID="${VERTEX_SESSION_RUNTIME_ID:-}"
VERTEX_MEMORY_BANK_ID="${VERTEX_MEMORY_BANK_ID:-}"
MEMORY_ENABLED="${MEMORY_ENABLED:-false}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
GEMINI_SEGMENTATION_MODEL="${GEMINI_SEGMENTATION_MODEL:-gemini-3.8-flash}"
GEMINI_TRANSCRIPTION_MODEL="${GEMINI_TRANSCRIPTION_MODEL:-gemini-3.8-flash}"
GEMINI_IMAGE_MODEL="${GEMINI_IMAGE_MODEL:-gemini-nano-banana-2.1}"

# Product search
PRODUCT_SEARCH_ENABLED="${PRODUCT_SEARCH_ENABLED:-true}"
PRODUCT_SEARCH_MODEL="${PRODUCT_SEARCH_MODEL:-gemini-3.8-flash}"
PRODUCT_SEARCH_COUNTRY="${PRODUCT_SEARCH_COUNTRY:-India}"
PRODUCT_SEARCH_TOP_K="${PRODUCT_SEARCH_TOP_K:-4}"
PRODUCT_SEARCH_TIMEOUT_SECONDS="${PRODUCT_SEARCH_TIMEOUT_SECONDS:-45}"
PRODUCT_SEARCH_RETRY_UNPARSEABLE="${PRODUCT_SEARCH_RETRY_UNPARSEABLE:-false}"

# Upload / streaming / logging
MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-80}"
MAX_TRANSCRIPTION_MB="${MAX_TRANSCRIPTION_MB:-10}"
SSE_HEARTBEAT_SECONDS="${SSE_HEARTBEAT_SECONDS:-10}"
ARTHISTICS_LOG_LEVEL="${ARTHISTICS_LOG_LEVEL:-INFO}"
ARTHISTICS_LOG_FORMAT="${ARTHISTICS_LOG_FORMAT:-auto}"

# Measurement defaults
CALIBRATION_MARKER_DICTIONARY="${CALIBRATION_MARKER_DICTIONARY:-DICT_4X4_50}"
CALIBRATION_MARKER_ID="${CALIBRATION_MARKER_ID:-23}"
CALIBRATION_MARKER_SIZE_MM="${CALIBRATION_MARKER_SIZE_MM:-100}"
A4_SHORT_SIDE_MM="${A4_SHORT_SIDE_MM:-210}"
A4_LONG_SIDE_MM="${A4_LONG_SIDE_MM:-297}"

# Cloud Run resources
MEMORY="${MEMORY:-2Gi}"
CPU="${CPU:-2}"
TIMEOUT="${TIMEOUT:-900}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-1}"
CONCURRENCY="${CONCURRENCY:-10}"

log()  { printf '\n\033[1;34m[INFO]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage:
  $0 PROJECT_ROOT ARTIFACT_BUCKET [RUNTIME_SERVICE_ACCOUNT]

Example:
  $0 \
    ~/iyal-lite-work/current \
    arthistics-artifacts \
    arthistics-backend-sa@my-project.iam.gserviceaccount.com
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

add_optional_env() {
  local name="$1"
  local value="${!name:-}"

  if [[ -n "$value" ]]; then
    ENV_VARS+=("$name=$value")
  fi
}

[[ -n "$PROJECT_ROOT" && -n "$GCS_BUCKET" ]] || {
  usage
  exit 2
}

require_cmd gcloud
require_cmd curl
require_cmd realpath

PROJECT_ROOT="$(realpath -e "$PROJECT_ROOT")"

[[ -d "$PROJECT_ROOT" ]] \
  || die "Project root does not exist: $PROJECT_ROOT"

# ------------------------------------------------------------
# Validate deployment-ready source
# ------------------------------------------------------------
[[ -f "$PROJECT_ROOT/backend/app/main.py" ]] \
  || die "Missing: $PROJECT_ROOT/backend/app/main.py"

[[ -f "$PROJECT_ROOT/backend/requirements.txt" ]] \
  || die "Missing: $PROJECT_ROOT/backend/requirements.txt"

[[ -d "$PROJECT_ROOT/backend/cad" ]] \
  || die "Missing: $PROJECT_ROOT/backend/cad"

[[ -f "$PROJECT_ROOT/frontend-lite/index.html" ]] \
  || die "Missing: $PROJECT_ROOT/frontend-lite/index.html"

[[ -f "$PROJECT_ROOT/site/index.html" ]] \
  || die "Missing landing page: $PROJECT_ROOT/site/index.html"

[[ -f "$PROJECT_ROOT/Dockerfile" ]] \
  || die "Missing root Dockerfile: $PROJECT_ROOT/Dockerfile"

[[ -f "$PROJECT_ROOT/.dockerignore" ]] \
  || warn "Root .dockerignore is missing."

[[ -f "$PROJECT_ROOT/.gcloudignore" ]] \
  || warn "Root .gcloudignore is missing."

[[ -f "$PROJECT_ROOT/.gitignore" ]] \
  || warn "Root .gitignore is missing."

[[ -n "$PROJECT_ID" ]] \
  || die "No Google Cloud project configured.

Run:
  gcloud config set project YOUR_PROJECT_ID"

log "Configuring Google Cloud project"
gcloud config set project "$PROJECT_ID" >/dev/null

ACTIVE_ACCOUNT="$(gcloud auth list \
  --filter=status:ACTIVE \
  --format='value(account)' | head -n1)"

[[ -n "$ACTIVE_ACCOUNT" ]] \
  || die "No active gcloud account."

log "Checking Google Cloud project"
gcloud projects describe "$PROJECT_ID" \
  --format='value(projectId)' >/dev/null

log "Checking artifact bucket"
gcloud storage buckets describe "gs://$GCS_BUCKET" \
  --project "$PROJECT_ID" >/dev/null \
  || die "Cannot access artifact bucket: gs://$GCS_BUCKET"

if [[ -n "$RUNTIME_SERVICE_ACCOUNT" ]]; then
  log "Checking Cloud Run runtime service account"
  gcloud iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT" \
    --project "$PROJECT_ID" >/dev/null \
    || die "Runtime service account not found or not accessible:
$RUNTIME_SERVICE_ACCOUNT"
fi

if [[ "$MEMORY_ENABLED" == "true" && -z "$VERTEX_MEMORY_BANK_ID" ]]; then
  die "MEMORY_ENABLED=true but VERTEX_MEMORY_BANK_ID is missing."
fi
if [[ -n "$VERTEX_MEMORY_BANK_ID" && -z "$VERTEX_SESSION_RUNTIME_ID" ]]; then
  warn "Memory Bank is configured without managed Sessions. This is supported, but stable cross-session user identity must be verified."
fi

# ------------------------------------------------------------
# Runtime environment variables
#
# --update-env-vars is used so variables not listed here are not
# intentionally deleted from an existing Cloud Run service.
# ------------------------------------------------------------
ENV_VARS=(
  "GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
  "GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION"
  "GOOGLE_GENAI_USE_VERTEXAI=TRUE"

  "GCS_BUCKET=$GCS_BUCKET"

  "GEMINI_MODEL=$GEMINI_MODEL"
  "GEMINI_SEGMENTATION_MODEL=$GEMINI_SEGMENTATION_MODEL"
  "GEMINI_TRANSCRIPTION_MODEL=$GEMINI_TRANSCRIPTION_MODEL"
  "GEMINI_IMAGE_MODEL=$GEMINI_IMAGE_MODEL"

  "PRODUCT_SEARCH_ENABLED=$PRODUCT_SEARCH_ENABLED"
  "PRODUCT_SEARCH_MODEL=$PRODUCT_SEARCH_MODEL"
  "PRODUCT_SEARCH_COUNTRY=$PRODUCT_SEARCH_COUNTRY"
  "PRODUCT_SEARCH_TOP_K=$PRODUCT_SEARCH_TOP_K"
  "PRODUCT_SEARCH_TIMEOUT_SECONDS=$PRODUCT_SEARCH_TIMEOUT_SECONDS"
  "PRODUCT_SEARCH_RETRY_UNPARSEABLE=$PRODUCT_SEARCH_RETRY_UNPARSEABLE"

  "OPENSCAD_BINARY=openscad"

  "MAX_UPLOAD_MB=$MAX_UPLOAD_MB"
  "MAX_TRANSCRIPTION_MB=$MAX_TRANSCRIPTION_MB"

  "SSE_HEARTBEAT_SECONDS=$SSE_HEARTBEAT_SECONDS"

  "ARTHISTICS_LOG_LEVEL=$ARTHISTICS_LOG_LEVEL"
  "ARTHISTICS_LOG_FORMAT=$ARTHISTICS_LOG_FORMAT"

  "CALIBRATION_MARKER_DICTIONARY=$CALIBRATION_MARKER_DICTIONARY"
  "CALIBRATION_MARKER_ID=$CALIBRATION_MARKER_ID"
  "CALIBRATION_MARKER_SIZE_MM=$CALIBRATION_MARKER_SIZE_MM"
  "A4_SHORT_SIDE_MM=$A4_SHORT_SIDE_MM"
  "A4_LONG_SIDE_MM=$A4_LONG_SIDE_MM"
)

# Add managed context values only when explicitly configured.
add_optional_env AGENT_PLATFORM_LOCATION
add_optional_env VERTEX_SESSION_RUNTIME_ID
add_optional_env VERTEX_MEMORY_BANK_ID
if [[ -n "$VERTEX_MEMORY_BANK_ID" ]]; then ENV_VARS+=("MEMORY_ENABLED=$MEMORY_ENABLED"); fi
add_optional_env SESSION_DB_URL

add_optional_env SMTP_HOST
add_optional_env SMTP_PORT
add_optional_env SMTP_USERNAME
add_optional_env SMTP_PASSWORD
add_optional_env SMTP_USE_TLS
add_optional_env SUPPORT_EMAIL_FROM

# Use a custom delimiter because some values can contain commas.
ENV_JOINED=""
for item in "${ENV_VARS[@]}"; do
  if [[ -z "$ENV_JOINED" ]]; then
    ENV_JOINED="$item"
  else
    ENV_JOINED+="|$item"
  fi
done

ENV_FLAG="^|^$ENV_JOINED"

RUNTIME_ARGS=()

if [[ -n "$RUNTIME_SERVICE_ACCOUNT" ]]; then
  RUNTIME_ARGS+=(--service-account "$RUNTIME_SERVICE_ACCOUNT")
fi

cat <<EOF

============================================================
 Iyal.ai Lite deployment
============================================================
 Project           : $PROJECT_ID
 Region            : $REGION
 Service           : $SERVICE_NAME
 Source            : $PROJECT_ROOT
 Artifact bucket   : gs://$GCS_BUCKET
 Runtime SA        : ${RUNTIME_SERVICE_ACCOUNT:-Cloud Run default}
 Build SA          : default Cloud Build service account
 Memory / CPU      : $MEMORY / $CPU
 Timeout           : ${TIMEOUT}s
 Min / Max         : $MIN_INSTANCES / $MAX_INSTANCES
 Concurrency       : $CONCURRENCY
 Sessions          : ${VERTEX_SESSION_RUNTIME_ID:-local/database fallback}
 Memory Bank       : ${VERTEX_MEMORY_BANK_ID:-disabled}
============================================================
EOF

# ------------------------------------------------------------
# Deploy directly from the project root.
#
# The project-root Dockerfile includes:
#   backend/app
#   backend/cad
#   backend/requirements.txt
#   frontend-lite
#
# .gcloudignore prevents local .venv/cache/etc. from being uploaded.
# .dockerignore prevents unnecessary files from entering Docker context.
# ------------------------------------------------------------
log "Deploying to Cloud Run"

gcloud run deploy "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source "$PROJECT_ROOT" \
  --allow-unauthenticated \
  --memory "$MEMORY" \
  --cpu "$CPU" \
  --timeout "$TIMEOUT" \
  --min-instances "$MIN_INSTANCES" \
  --max-instances "$MAX_INSTANCES" \
  --concurrency "$CONCURRENCY" \
  --update-env-vars "$ENV_FLAG" \
  "${RUNTIME_ARGS[@]}" \
  --quiet

# ------------------------------------------------------------
# Resolve deployed service information
# ------------------------------------------------------------
SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')"

REVISION="$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.latestReadyRevisionName)')"

[[ -n "$SERVICE_URL" ]] \
  || die "Deployment completed but Cloud Run URL could not be resolved."

ok "Cloud Run deployment completed"

# ------------------------------------------------------------
# Basic checks
# ------------------------------------------------------------
log "Checking Lite UI"

if curl -fsS --max-time 30 "$SERVICE_URL/app/" >/dev/null; then
  ok "Lite UI responded successfully"
else
  warn "Cloud Run deployed, but /app/ did not return success."
fi

log "Checking backend health"

if curl -fsS --max-time 30 "$SERVICE_URL/health" >/dev/null; then
  ok "Backend health check passed"
else
  warn "/health did not return success. If your backend does not expose /health, this warning can be ignored."
fi

cat <<EOF

============================================================
 Iyal.ai Lite deployed successfully
============================================================
 Service URL : $SERVICE_URL
 Lite UI     : $SERVICE_URL/app/
 Revision    : $REVISION
 Project     : $PROJECT_ID
 Region      : $REGION
============================================================

Open:
  $SERVICE_URL/app/

Cloud Run logs:
  gcloud run services logs read "$SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --limit 100

After changing source code, redeploy with the same command:
  $0 "$PROJECT_ROOT" "$GCS_BUCKET" "$RUNTIME_SERVICE_ACCOUNT"

You do NOT need to download/unzip the ZIP again after local edits.
============================================================
EOF
