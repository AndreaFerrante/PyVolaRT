#!/usr/bin/env bash
# One-command start: backend (FastAPI) + frontend (Vite). Ctrl+C stops both.
#   ./start.sh          simulated feed (no broker)
#   ./start.sh ibkr     live IBKR feed (TWS must be running with the API enabled)
set -euo pipefail
cd "$(dirname "$0")"

provider="${1:-simulated}"

if [ ! -x backend/.venv/bin/python ]; then
  echo "creating backend/.venv"
  python3 -m venv backend/.venv
fi
# reinstall only when requirements change
if [ ! -f backend/.venv/.installed ] || [ backend/requirements.txt -nt backend/.venv/.installed ]; then
  backend/.venv/bin/pip install -q -r backend/requirements.txt
  touch backend/.venv/.installed
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
[ -d frontend/node_modules ] || (cd frontend && npm install)

trap 'kill 0' EXIT
(cd backend && GEX_PROVIDER="$provider" .venv/bin/uvicorn app.main:app --port 8000) &
(cd frontend && npm run dev -- --port 5173) &

echo "provider=$provider  dashboard: http://localhost:5173  api: http://127.0.0.1:8000/docs"
wait
