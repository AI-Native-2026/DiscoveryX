#!/usr/bin/env bash
# Run a MetAP2 task and verify the new LLM touchpoints + metering.
set -uo pipefail
BASE=http://localhost:8000/api/v1
SCI=(-H "X-Role: scientist" -H "X-User: alice")
JSON=(-H "Content-Type: application/json")

echo "=== clear stale tasks ==="
docker exec dx-redis redis-cli del dx:tasks:index arq:queue >/dev/null 2>&1 || true
docker exec dx-redis redis-cli --scan --pattern 'dx:task:*' 2>/dev/null | tr -d '\r' | while read -r k; do
  [ -n "$k" ] && docker exec dx-redis redis-cli del "$k" >/dev/null 2>&1
done
echo "  done"

TASK=$(curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/tasks" \
  -d '{"hypothesis":"寻找对 MetAP2 高活性、可穿透血脑屏障且无肝毒性的小分子","dataset_id":"chembl_metap2_activities","activity_model":"qsar","rounds":3,"objectives":["BBB","hepatotoxicity"],"project":"metap2"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['task_id'])")
echo "  task=$TASK"
for i in $(seq 1 100); do
  sleep 3
  ST=$(curl -s "${SCI[@]}" "$BASE/tasks/$TASK" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
  case "$ST" in succeeded|failed|blocked) echo "  [$i] $ST"; break;; esac
done

echo
echo "=== LLM calls recorded for this run (worker log) ==="
grep -h "$TASK" "$HOME"/discoveryx/logs/worker.log 2>/dev/null | grep 'llm call' | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    print('  %-18s prompt=%-5s completion=%-5s' % (d.get('purpose'), d.get('prompt_tokens'), d.get('completion_tokens')))
" || echo "  (none matched by task id; showing recent)"

echo
echo "=== task token_usage ==="
curl -s "${SCI[@]}" "$BASE/tasks/$TASK" | python3 -c "
import sys, json
d = json.load(sys.stdin); u = d['token_usage']; r = d.get('result') or {}
print('  calls=%s  in=%s  out=%s  cost=%s' % (u['calls'], u['prompt_tokens'], u['completion_tokens'], u['cost_usd']))
print()
print('  target_summary:', (r.get('target_summary') or '(none)')[:220])
print()
for rd in (r.get('rounds') or []):
    print('  R%s narrative: %s' % (rd['round'], (rd.get('narrative') or '(none)')[:200]))
"
echo
echo "=== report section 8 (run manifest) ==="
curl -s "${SCI[@]}" "$BASE/tasks/$TASK/report" -o /tmp/r4.html
python3 - <<'PY'
import re, pathlib, html
h = pathlib.Path('/tmp/r4.html').read_text(encoding='utf-8')
sec = h.split('8. 运行清单')[1].split('</div>\n  </div>')[0]
for k, v in re.findall(r'<div class="kv"><span>(.*?)</span><span>(.*?)</span></div>', sec):
    print('  %-22s %s' % (html.unescape(k), html.unescape(re.sub('<[^>]+>', '', v))))
print()
print('  has Token 账单 card:', 'Token 账单' in h)
print('  has 靶点情报摘要  :', '靶点情报摘要' in h)
PY
echo
echo "TASK=$TASK"
