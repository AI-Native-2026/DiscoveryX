#!/usr/bin/env bash
set -uo pipefail
cd "$HOME/discoveryx" || exit 1

echo "=== datasets on the VM ==="
for d in data/datasets/*/; do
  [ -d "$d" ] || continue
  id=$(basename "$d")
  n=$(find "$d" -type f | wc -l | tr -d ' ')
  sens=$(python3 -c "
import json,pathlib
p=pathlib.Path('$d/dataset.json')
try: print(json.loads(p.read_text(encoding='utf-8')).get('sensitivity','?'))
except Exception: print('?')
")
  printf '  %-26s files=%-4s sensitivity=%s\n' "$id" "$n" "$sens"
done

echo
echo "=== runtime state ==="
printf '  projects.json   : %s\n' "$(python3 -c "import json;print(len(json.load(open('data/projects.json',encoding='utf-8'))),'project(s)')" 2>/dev/null || echo 'n/a')"
printf '  approvals.json  : %s\n' "$(python3 -c "import json;print(len(json.load(open('data/approvals.json',encoding='utf-8'))),'approval(s)')" 2>/dev/null || echo 'n/a')"
printf '  models          : %s\n' "$(ls data/models 2>/dev/null | wc -l | tr -d ' ') file(s)"
printf '  chroma          : %s\n' "$(du -sh data/chroma 2>/dev/null | cut -f1)"
printf '  audit log       : %s\n' "$(wc -l < data/audit/audit.jsonl 2>/dev/null || echo 0) line(s)"

echo
echo "=== services ==="
for s in discoveryx-api discoveryx-worker; do printf '  %-22s %s\n' "$s" "$(systemctl is-active $s.service)"; done
printf '  %-22s %s\n' "frontend :8080" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/)"
printf '  %-22s %s\n' "api :8000" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/health)"
