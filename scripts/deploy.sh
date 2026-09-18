#!/usr/bin/env bash
# DiscoveryX — idempotent one-command deploy for a Linux host.
#
#   scripts/deploy.sh                  full deploy: deps -> data -> build -> services
#   scripts/deploy.sh --skip-data      reuse the datasets already on disk
#   scripts/deploy.sh --skip-frontend  backend only (no SPA build)
#   scripts/deploy.sh --check          preflight checks only, change nothing
#
# Environment overrides:
#   APP_DIR    repository/install root (default: the repo containing this script)
#   PORT       API port                (default: 8000)
#   WEB_PORT   static frontend port    (default: 8080)
#   VENV       python venv path        (default: $APP_DIR/backend/.venv)
#
# Re-running is safe: every step checks the current state first.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PORT="${PORT:-8000}"
WEB_PORT="${WEB_PORT:-8080}"
VENV="${VENV:-$APP_DIR/backend/.venv}"

SKIP_DATA=0
SKIP_FRONTEND=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-data) SKIP_DATA=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[36m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

log "app dir: $APP_DIR   api: :$PORT   web: :$WEB_PORT"

# --------------------------------------------------------------- 1. preflight
log "1/8 preflight"
have python3 || die "python3 not found"
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
python3 - <<'PY' || die "python 3.11+ is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
log "   python $PYV"

if [ "$SKIP_FRONTEND" -eq 0 ]; then
  have node || die "node not found (needed for the frontend build)"
  NODEMAJ=$(node -v | sed 's/^v\([0-9]*\).*/\1/')
  [ "$NODEMAJ" -ge 20 ] || die "node 20+ is required (found $(node -v))"
  have npm || die "npm not found"
  log "   node $(node -v)"
fi

REDIS_MODE=""
if (echo > "/dev/tcp/127.0.0.1/6379") >/dev/null 2>&1; then
  REDIS_MODE="running"
elif have docker; then
  REDIS_MODE="docker"
elif have redis-server; then
  REDIS_MODE="local"
else
  die "no Redis on :6379 and neither docker nor redis-server is available"
fi
log "   redis: $REDIS_MODE"

if [ "$CHECK_ONLY" -eq 1 ]; then
  log "preflight OK (--check, nothing changed)"
  exit 0
fi

# ------------------------------------------------------------------- 2. env
log "2/8 environment file"
if [ ! -f "$APP_DIR/.env" ]; then
  [ -f "$APP_DIR/.env.example" ] || die ".env.example missing"
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  warn "created $APP_DIR/.env from .env.example — set DEEPSEEK_API_KEY for LLM-backed features"
else
  log "   .env present"
fi

# --------------------------------------------------------------- 3. backend
log "3/8 backend dependencies"
if [ ! -x "$VENV/bin/python" ]; then
  if have uv; then
    log "   creating venv at $VENV (uv, python 3.11)"
    uv venv --python 3.11 "$VENV" || python3 -m venv "$VENV" || die "venv creation failed"
  else
    log "   creating venv at $VENV"
    python3 -m venv "$VENV" || die "venv creation failed (install python3-venv?)"
  fi
fi
if have uv; then
  VIRTUAL_ENV="$VENV" uv pip install -q -r "$APP_DIR/backend/requirements.txt" \
    || die "backend dependency install failed"
else
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -q -r "$APP_DIR/backend/requirements.txt" \
    || die "backend dependency install failed"
fi
log "   installed ($("$VENV/bin/python" -c 'import sys;print("%d.%d"%sys.version_info[:2])'))"

# ------------------------------------------------------------------ 4. data
log "4/8 datasets"
DATASETS_DIR="$APP_DIR/data/datasets"
N_DATASETS=$(find "$DATASETS_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
if [ "$SKIP_DATA" -eq 1 ]; then
  log "   skipped (--skip-data), $N_DATASETS dataset(s) on disk"
elif [ "${N_DATASETS:-0}" -gt 0 ]; then
  log "   $N_DATASETS dataset(s) already present (remove data/datasets/<id> to rebuild one)"
else
  log "   building from public sources (ChEMBL / MoleculeNet / PDB / Europe PMC)"
  (cd "$APP_DIR" && "$VENV/bin/python" data/download_data.py --index) \
    || warn "dataset build failed — rerun: $VENV/bin/python data/download_data.py --index"
fi

# -------------------------------------------------------------- 5. frontend
log "5/8 frontend build"
if [ "$SKIP_FRONTEND" -eq 1 ]; then
  log "   skipped (--skip-frontend)"
else
  (cd "$APP_DIR/frontend" \
    && { npm ci --silent 2>/dev/null || npm install --silent; } \
    && VITE_API_BASE="${VITE_API_BASE:-http://localhost:$PORT}" npm run build --silent) \
    || die "frontend build failed"
  log "   built $APP_DIR/frontend/dist"
fi

# ----------------------------------------------------------------- 6. redis
log "6/8 redis"
if [ "$REDIS_MODE" = "running" ]; then
  log "   already listening on :6379"
elif [ "$REDIS_MODE" = "docker" ]; then
  if docker ps -a --format '{{.Names}}' | grep -qx dx-redis; then
    docker start dx-redis >/dev/null && log "   started existing container dx-redis"
  else
    docker run -d --name dx-redis -p 6379:6379 redis:7-alpine >/dev/null \
      && log "   started container dx-redis"
  fi
else
  redis-server --daemonize yes && log "   started local redis-server"
fi

# -------------------------------------------------------------- 7. services
log "7/8 api + worker"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

USE_SYSTEMD=0
if have systemctl && sudo -n true 2>/dev/null; then
  USE_SYSTEMD=1
fi

if [ "$USE_SYSTEMD" -eq 1 ]; then
  sudo tee /etc/systemd/system/discoveryx-api.service >/dev/null <<EOF
[Unit]
Description=DiscoveryX API (FastAPI + uvicorn)
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
ExecStart=$VENV/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/api.log
StandardError=append:$LOG_DIR/api.log

[Install]
WantedBy=multi-user.target
EOF

  sudo tee /etc/systemd/system/discoveryx-worker.service >/dev/null <<EOF
[Unit]
Description=DiscoveryX Worker (ARQ)
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
ExecStart=$VENV/bin/arq app.tasks.worker.WorkerSettings
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/worker.log
StandardError=append:$LOG_DIR/worker.log

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable discoveryx-api discoveryx-worker >/dev/null 2>&1
  sudo systemctl restart discoveryx-api discoveryx-worker
  log "   systemd units installed and restarted"
else
  warn "systemd/sudo unavailable — falling back to nohup (no auto-restart)"
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "arq app.tasks.worker" 2>/dev/null || true
  sleep 1
  (cd "$APP_DIR/backend" && nohup "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$PORT" >"$LOG_DIR/api.log" 2>&1 &)
  (cd "$APP_DIR/backend" && nohup "$VENV/bin/arq" app.tasks.worker.WorkerSettings >"$LOG_DIR/worker.log" 2>&1 &)
  log "   started via nohup"
fi

# -------------------------------------------------------------- 8. frontend
if [ "$SKIP_FRONTEND" -eq 0 ]; then
  log "8/8 serving frontend on :$WEB_PORT"
  if [ "$USE_SYSTEMD" -eq 1 ]; then
    sudo tee /etc/systemd/system/discoveryx-web.service >/dev/null <<EOF
[Unit]
Description=DiscoveryX static frontend
After=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR/frontend/dist
ExecStart=$(command -v python3) -m http.server $WEB_PORT --bind 0.0.0.0
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/web.log
StandardError=append:$LOG_DIR/web.log

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable discoveryx-web >/dev/null 2>&1
    sudo systemctl restart discoveryx-web
    log "   systemd unit discoveryx-web restarted"
  else
    pkill -f "http.server $WEB_PORT" 2>/dev/null || true
    sleep 1
    (cd "$APP_DIR/frontend/dist" && nohup python3 -m http.server "$WEB_PORT" --bind 0.0.0.0 >"$LOG_DIR/web.log" 2>&1 &)
    log "   started via nohup"
  fi
else
  log "8/8 frontend skipped"
fi

# ------------------------------------------------------------------ verify
log "waiting for the API…"
HEALTH=""
for _ in $(seq 1 30); do
  HEALTH=$(curl -fsS "http://localhost:$PORT/api/v1/health" 2>/dev/null || true)
  [ -n "$HEALTH" ] && break
  sleep 2
done

echo
log "================ SUMMARY ================"
if [ -n "$HEALTH" ]; then
  printf '  api      : ok  %s\n' "$HEALTH"
else
  printf '  api      : NOT RESPONDING — see %s/api.log\n' "$LOG_DIR"
fi
if [ "$SKIP_FRONTEND" -eq 0 ]; then
  printf '  web      : http://localhost:%s\n' "$WEB_PORT"
fi
printf '  api docs : http://localhost:%s/docs\n' "$PORT"
printf '  datasets : %s\n' "$N_DATASETS"
printf '  logs     : %s\n' "$LOG_DIR"
log "========================================="
