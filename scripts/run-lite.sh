#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
PYTHON="${PYTHON:-python}"

[[ -f "$ROOT/backend/.env" ]] || {
  echo "Create backend/.env from backend/.env.example first." >&2
  exit 1
}

cd "$ROOT/backend"
echo "Iyal.ai v0.13.2 Lite: http://127.0.0.1:$PORT/ (chat at /app/)"
echo "No Node.js/npm frontend build is required."
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload
