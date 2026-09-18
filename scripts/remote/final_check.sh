#!/usr/bin/env bash
set -uo pipefail
BASE=http://localhost:8000/api/v1
AUTH=(-H "X-Role: scientist" -H "X-User: alice")

echo "=== projects ==="
curl -s "${AUTH[@]}" "$BASE/projects" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  total', d['total'])
for p in d['items']:
    print('  %-8s | %-16s | %-6s | %s' % (p['id'], p['name'], p['target'], ','.join(p['objectives'])))
"

echo
echo "=== tasks (newest first) ==="
curl -s "${AUTH[@]}" "$BASE/tasks" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  total', len(d))
for t in d:
    print('  %-16s %-10s %-8s proj=%-8s ds=%s' % (t['task_id'], t['status'], t['stage'], t.get('project'), t.get('dataset_id')))
"

echo
echo "=== per-project isolation ==="
for p in bace1 egfr egfr-2; do
  n=$(curl -s "${AUTH[@]}" "$BASE/tasks?project=$p" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
  echo "  project=$p -> $n task(s)"
done
n=$(curl -s "${AUTH[@]}" "$BASE/tasks?project=does-not-exist" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "  project=does-not-exist -> $n task(s)"

echo
echo "=== decisions ==="
for t in $(curl -s "${AUTH[@]}" "$BASE/tasks" | python3 -c "
import sys, json
for t in json.load(sys.stdin):
    print(t['task_id'])
"); do
  curl -s "${AUTH[@]}" "$BASE/tasks/$t" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d.get('result') or {}
print('  %-16s rounds=%d  proj=%-8s %s' % (d['task_id'], len(r.get('rounds') or []), d.get('project'), r.get('decision')))
"
done

echo
echo "=== services ==="
for s in discoveryx-api discoveryx-worker; do
  printf "  %-20s %s\n" "$s" "$(systemctl is-active $s.service)"
done
