#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Iyal.ai Lite - Download and prepare source from GCS
#
# Usage:
#   ./prepare-lite.sh gs://BUCKET/path/iyal-v0.13.0.zip
#
# Optional custom work directory:
#   ./prepare-lite.sh \
#     gs://BUCKET/path/iyal-v0.13.0.zip \
#     ~/arthistics-lite-work
#
# Result:
#   ~/arthistics-lite-work/<release-name>/source/...
#   ~/arthistics-lite-work/current -> detected project root
#
# This script DOES NOT deploy anything.
# It intentionally keeps the extracted source so you can edit it.
# ============================================================

ZIP_URI="${1:-}"
WORK_BASE="${2:-$HOME/arthistics-lite-work}"

log()  { printf '\n\033[1;34m[INFO]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage:
  $0 gs://BUCKET/path/iyal-v0.13.0.zip [WORK_BASE]

Example:
  $0 gs://my-code-bucket/releases/iyal-v0.13.0.zip

Default work folder:
  $HOME/arthistics-lite-work
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

[[ -n "$ZIP_URI" ]] || { usage; exit 2; }
[[ "$ZIP_URI" == gs://*.zip ]] || die "First argument must be a gs://...zip URI."

require_cmd gcloud
require_cmd unzip
require_cmd find
require_cmd basename
require_cmd dirname

RELEASE_NAME="$(basename "$ZIP_URI" .zip)"
RELEASE_DIR="$WORK_BASE/$RELEASE_NAME"
ZIP_FILE="$RELEASE_DIR/$RELEASE_NAME.zip"
SOURCE_DIR="$RELEASE_DIR/source"
CURRENT_LINK="$WORK_BASE/current"

log "Checking GCS ZIP"
gcloud storage ls "$ZIP_URI" >/dev/null \
  || die "Cannot access ZIP: $ZIP_URI"

if [[ -e "$RELEASE_DIR" ]]; then
  die "Release work folder already exists:

  $RELEASE_DIR

It may contain manual edits, so this script will not overwrite it.

To start again from the ZIP:
  rm -rf \"$RELEASE_DIR\"

Then rerun this script."
fi

mkdir -p "$SOURCE_DIR"

log "Downloading ZIP from GCS"
gcloud storage cp "$ZIP_URI" "$ZIP_FILE" --quiet
ok "Downloaded: $ZIP_FILE"

log "Extracting ZIP"
unzip -q "$ZIP_FILE" -d "$SOURCE_DIR"
ok "Extracted: $SOURCE_DIR"

# ------------------------------------------------------------
# Locate the project root.
# Expected root contains:
#   backend/app/main.py
#   backend/requirements.txt
#   frontend-lite/index.html
#   Dockerfile
# ------------------------------------------------------------
PROJECT_ROOT=""

is_project_root() {
  local candidate="$1"

  [[ -f "$candidate/backend/app/main.py" ]] &&
  [[ -f "$candidate/backend/requirements.txt" ]] &&
  [[ -f "$candidate/frontend-lite/index.html" ]] &&
  [[ -f "$candidate/Dockerfile" ]]
}

if is_project_root "$SOURCE_DIR"; then
  PROJECT_ROOT="$SOURCE_DIR"
else
  while IFS= read -r main_file; do
    # .../<root>/backend/app/main.py -> <root>
    candidate="$(dirname "$(dirname "$(dirname "$main_file")")")"

    if is_project_root "$candidate"; then
      PROJECT_ROOT="$candidate"
      break
    fi
  done < <(find "$SOURCE_DIR" -type f -path '*/backend/app/main.py' -print)
fi

[[ -n "$PROJECT_ROOT" ]] || die "Could not find the Iyal.ai Lite project root.

Expected files:
  backend/app/main.py
  backend/requirements.txt
  frontend-lite/index.html
  Dockerfile"

mkdir -p "$WORK_BASE"
ln -sfn "$PROJECT_ROOT" "$CURRENT_LINK"

# Optional deployment-support files should exist in the proper package.
for f in .gitignore .dockerignore .gcloudignore; do
  if [[ ! -f "$PROJECT_ROOT/$f" ]]; then
    warn "$f is not present in the extracted package."
  fi
done

cat <<EOF

============================================================
 Iyal.ai Lite source is ready
============================================================
 Release       : $RELEASE_NAME
 GCS ZIP       : $ZIP_URI

 Project root  : $PROJECT_ROOT
 Current link  : $CURRENT_LINK

You can edit the source here:
  cd "$CURRENT_LINK"

For example:
  cloudshell edit "$CURRENT_LINK/backend/requirements.txt"

Deploy when ready:
  ./deploy-lite.sh "$CURRENT_LINK" YOUR_ARTIFACT_BUCKET YOUR_RUNTIME_SERVICE_ACCOUNT
============================================================
EOF
