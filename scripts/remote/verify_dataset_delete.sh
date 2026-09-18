#!/usr/bin/env bash
# Verify dataset deletion: RBAC, clearance, path safety and the actual removal.
set -uo pipefail
BASE=http://localhost:8000/api/v1
JSON=(-H "Content-Type: application/json")
SCI=(-H "X-Role: scientist" -H "X-User: alice")
ENG=(-H "X-Role: engineer" -H "X-User: bob")

echo "=== 1. create a throwaway dataset ==="
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/datasets" \
  -d '{"id":"tmp_delete_me","name":"Throwaway","data_type":"tabular","sensitivity":"public","purpose":"tool","source":"test"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('   created:', d.get('id'))"
mkdir -p "$HOME/discoveryx/data/datasets/tmp_delete_me"
printf 'smiles,pIC50\nCCO,5.0\n' > "$HOME/discoveryx/data/datasets/tmp_delete_me/tmp.csv"
echo "   on disk: $(ls "$HOME/discoveryx/data/datasets/tmp_delete_me" 2>/dev/null | tr '\n' ' ')"

echo
echo "=== 2. scientist tries to delete (expect 403, needs dataset:delete) ==="
curl -s -o /tmp/d1.json -w "   HTTP %{http_code}\n" "${JSON[@]}" "${SCI[@]}" -X DELETE "$BASE/datasets/tmp_delete_me"
python3 -c "import json;print('   ', json.load(open('/tmp/d1.json')).get('message'))"

echo
echo "=== 3. engineer deletes it (expect 200) ==="
curl -s -o /tmp/d2.json -w "   HTTP %{http_code}\n" "${ENG[@]}" -X DELETE "$BASE/datasets/tmp_delete_me"
python3 -c "import json;print('   ', json.load(open('/tmp/d2.json')))"

echo
echo "=== 4. gone from disk and from the catalog? ==="
[ -d "$HOME/discoveryx/data/datasets/tmp_delete_me" ] && echo "   !! directory still present" || echo "   directory removed"
curl -s "${SCI[@]}" "$BASE/datasets" | python3 -c "
import sys, json
ids = [d['id'] for d in json.load(sys.stdin)['items']]
print('   in catalog:', 'tmp_delete_me' in ids)
"

echo
echo "=== 5. path traversal is rejected ==="
for bad in '../../etc' 'a/b' '.hidden'; do
  code=$(curl -s -o /tmp/d3.json -w '%{http_code}' "${ENG[@]}" -X DELETE "$BASE/datasets/$bad")
  echo "   DELETE /datasets/$bad -> HTTP $code"
done

echo
echo "=== 6. deleting a missing dataset -> 404 ==="
curl -s -o /dev/null -w "   HTTP %{http_code}\n" "${ENG[@]}" -X DELETE "$BASE/datasets/no_such_dataset"
