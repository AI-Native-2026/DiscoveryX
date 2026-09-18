#!/usr/bin/env bash
# Make the API and worker resilient: systemd units with Restart=always
set -uo pipefail

echo "=== stop legacy nohup processes ==="
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "arq app.tasks.worker" 2>/dev/null || true
sleep 3

echo "=== prepare log dir ==="
mkdir -p "$HOME/discoveryx/logs"
touch "$HOME/discoveryx/logs/api.log" "$HOME/discoveryx/logs/worker.log"

echo "=== install systemd units ==="
sudo tee /etc/systemd/system/discoveryx-api.service >/dev/null <<'EOF'
[Unit]
Description=DiscoveryX API (FastAPI + uvicorn)
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/discoveryx/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
ExecStart=/home/ubuntu/discoveryx/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=append:/home/ubuntu/discoveryx/logs/api.log
StandardError=append:/home/ubuntu/discoveryx/logs/api.log

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/discoveryx-worker.service >/dev/null <<'EOF'
[Unit]
Description=DiscoveryX Worker (ARQ)
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/discoveryx/backend
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
ExecStart=/home/ubuntu/discoveryx/backend/.venv/bin/arq app.tasks.worker.WorkerSettings
Restart=always
RestartSec=3
StandardOutput=append:/home/ubuntu/discoveryx/logs/worker.log
StandardError=append:/home/ubuntu/discoveryx/logs/worker.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now discoveryx-api.service discoveryx-worker.service >/dev/null 2>&1
sleep 10

echo
echo "=== systemd status ==="
for s in discoveryx-api discoveryx-worker; do
  printf "  %-22s %s\n" "$s" "$(systemctl is-active $s.service) / $(systemctl is-enabled $s.service 2>/dev/null)"
done

echo
echo "=== api health ==="
curl -s http://localhost:8000/api/v1/health; echo

echo
echo "=== worker log ==="
tail -3 /home/ubuntu/discoveryx/logs/worker.log
