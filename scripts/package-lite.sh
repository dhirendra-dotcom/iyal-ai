#!/usr/bin/env bash
set -Eeuo pipefail

# Create a clean source ZIP without .venv, caches, secrets or generated output.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/dist/iyal-v0.13.2.zip}"

command -v zip >/dev/null 2>&1 || { echo "zip command is required." >&2; exit 1; }
mkdir -p "$(dirname "$DEST")"
[[ ! -e "$DEST" ]] || { echo "Refusing to overwrite: $DEST" >&2; exit 1; }

cd "$ROOT"
zip -qr "$DEST" . \
  -x '.git/*' \
     '*/.venv/*' '*/venv/*' \
     '*/__pycache__/*' '*/.pytest_cache/*' \
     '*.pyc' '*.pyo' \
     '*/.env' '*/.env.*' \
     'backend/demo_outputs/*' 'backend/artifacts/*' 'backend/tmp/*' 'backend/temp/*' \
     '*/node_modules/*' '*/.next/*' \
     'dist/*' 'build/*' '*.log'

echo "Created $DEST"
