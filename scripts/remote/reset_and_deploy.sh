#!/usr/bin/env bash
# Reset the platform to a clean, user-created-only state and restart services.
set -uo pipefail
cd "$HOME/discoveryx" || exit 1

echo "=== reset projects and approvals (start empty) ==="
echo '[]' > data/projects.json
echo '[]' > data/approvals.json
echo "  done"

echo "=== clear queued tasks ==="
docker exec dx-redis redis-cli del arq:queue dx:tasks:index >/dev/null 2>&1 || true
docker exec dx-redis redis-cli --scan --pattern 'dx:task:*' 2>/dev/null | tr -d '\r' | while read -r k; do
  [ -n "$k" ] && docker exec dx-redis redis-cli del "$k" >/dev/null 2>&1
done
echo "  done"

echo "=== datasets ==="
ls -1 data/datasets 2>/dev/null | sed 's/^/    /'

echo "=== restart services ==="
sudo systemctl restart discoveryx-api discoveryx-worker
sleep 8
systemctl is-active discoveryx-api discoveryx-worker

echo
echo "=== health ==="
curl -s http://localhost:8000/api/v1/health; echo
echo "=== projects (expect empty) ==="
curl -s -H "X-Role: scientist" http://localhost:8000/api/v1/projects; echo
