#!/usr/bin/env bash
# Build one ChEMBL target dataset and run a DMTA task, reporting candidate ADMET.
#   usage: bash try_target.sh <dataset_id> <target_name> <pdb_id> <objectives_json> <project_name>
set -uo pipefail
BASE=http://localhost:8000/api/v1
SCI=(-H "X-Role: scientist" -H "X-User: alice")
JSON=(-H "Content-Type: application/json")

DS=${1:-chembl_casp3_activities}
TARGET=${2:-Caspase-3}
PDB=${3:-1CP3}
OBJ=${4:-'["hepatotoxicity","solubility"]'}
PNAME=${5:-Caspase-3 抑制剂优化}

echo "=== build $DS ==="
cd "$HOME/discoveryx" || exit 1
backend/.venv/bin/python data/download_data.py --only "$DS" 2>&1 | tail -3

echo
echo "=== dataset ==="
curl -s "${SCI[@]}" "$BASE/datasets/$DS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = (d.get('meta') or {}).get('compound') or {}
print('   n_files=%s  activity_column=%s  usable=%s  molecules=%s'
      % (d['n_files'], c.get('activity_column'), c.get('usable_for_dmta'), (d.get('meta') or {}).get('n_molecules')))
"

echo
echo "=== project + task ==="
PID=$(curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/projects" \
  -d "{\"name\":\"$PNAME\",\"description\":\"针对 $TARGET 的抑制剂优化\",\"target\":\"$TARGET\",\"pdb_id\":\"$PDB\",\"objectives\":$OBJ}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
TASK=$(curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/tasks" \
  -d "{\"hypothesis\":\"寻找对 $TARGET 高活性且成药性良好的小分子\",\"dataset_id\":\"$DS\",\"activity_model\":\"qsar\",\"rounds\":3,\"objectives\":$OBJ,\"project\":\"$PID\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['task_id'])")
echo "   project=$PID  task=$TASK"

for i in $(seq 1 100); do
  sleep 3
  LINE=$(curl -s "${SCI[@]}" "$BASE/tasks/$TASK" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['stage'],str(d['round'])+'/'+str(d['rounds']))")
  case "$LINE" in
    queued*|running*) [ $((i % 5)) -eq 0 ] && echo "   [$i] $LINE";;
    *) echo "   [$i] $LINE"; break;;
  esac
done

echo
echo "=== result ==="
curl -s "${SCI[@]}" "$BASE/tasks/$TASK" | OBJ="$OBJ" python3 -c "
import os, sys, json
d = json.load(sys.stdin); r = d.get('result') or {}
md = r.get('activity_model') or {}
print('   molecules : %s' % (r.get('dataset') or {}).get('n_with_activity'))
print('   qsar      : %s' % md.get('metrics'))
print('   decision  : %s' % r.get('decision'))
for rd in r.get('rounds', []):
    print('   R%s  %s' % (rd['round'], rd['summary']))
    if rd.get('action'):
        print('        %s' % rd['action'])
print()
print('   %-3s %-7s %-6s %-6s %-6s %-7s %-6s %s' % ('#','pIC50','BBB','肝毒','hERG','Sol','MPO','SMILES'))
for c in (r.get('top_candidates') or []):
    print('   %-3s %-7s %-6s %-6s %-6s %-7s %-6s %s' % (
        c['id'], c.get('pIC50'), c.get('bbb'), c.get('hepatotoxic'),
        round(c.get('herg') or 0, 2), round(c.get('solubility') or 0, 2),
        c.get('mpo'), (c.get('smiles') or '')[:44]))
"
echo
echo "TASK=$TASK PROJECT=$PID"
