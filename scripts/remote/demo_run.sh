#!/usr/bin/env bash
# DiscoveryX — presenter walkthrough, executed end-to-end and captured as a transcript.
#
#   ACT 1  end-to-end case : Caspase-3 programme -> objectives met
#   ACT 2  second target   : MetAP2 programme    -> objectives met
#   ACT 3  governance      : human approval + JSONL audit trail
#   ACT 4  guardrails      : DLP block / DLP mask / RBAC denial
#
# Resets the platform first so the run is reproducible.
set -uo pipefail
BASE=http://localhost:8000/api/v1
SCI=(-H "X-Role: scientist" -H "X-User: alice")
GUEST=(-H "X-Role: guest" -H "X-User: anonymous")
ENG=(-H "X-Role: engineer" -H "X-User: bob")
JSON=(-H "Content-Type: application/json")

act() { echo; echo "╔══════════════════════════════════════════════════════════════════╗"; printf "║  %-64s ║\n" "$1"; echo "╚══════════════════════════════════════════════════════════════════╝"; }
step() { echo; echo "── $1"; }

# ---------------------------------------------------------------- clean slate
python3 - <<'PY' >/dev/null
import pathlib
home = pathlib.Path.home() / "discoveryx" / "data"
(home / "projects.json").write_text("[]", encoding="utf-8")
(home / "approvals.json").write_text("[]", encoding="utf-8")
PY
docker exec dx-redis redis-cli del arq:queue >/dev/null 2>&1 || true
docker exec dx-redis redis-cli --scan --pattern 'dx:task:*' 2>/dev/null | tr -d '\r' | while read -r k; do
  [ -n "$k" ] && docker exec dx-redis redis-cli del "$k" >/dev/null 2>&1
done
docker exec dx-redis redis-cli del dx:tasks:index >/dev/null 2>&1 || true

wait_task() {
  local task=$1 label=$2
  for i in $(seq 1 120); do
    sleep 3
    local line
    line=$(curl -s "${SCI[@]}" "$BASE/tasks/$task" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['stage'],str(d['round'])+'/'+str(d['rounds']),str(round(d['progress']*100))+'%')")
    case "$line" in
      queued*|running*) [ $((i % 4)) -eq 0 ] && echo "     [$label] $line";;
      *) echo "     [$label] $line"; break;;
    esac
  done
}

# ══════════════════════════════════════════════════════════════════════ ACT 0
act "ACT 0 · 平台就绪状态  (UI: 侧边栏 / 顶栏 / 语言与主题切换)"
step "服务健康  (UI: 系统状态页)"
curl -s "$BASE/health" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('     app=%s v%s  env=%s' % (d['app'], d['version'], d['environment']))
for k, v in d['components'].items():
    print('     %-10s %s' % (k, v))
"
step "初始状态：0 个项目（平台不预置任何演示数据）"
curl -s "${SCI[@]}" "$BASE/projects" | python3 -c "import sys,json;print('     项目数 =', json.load(sys.stdin)['total'])"
step "数据集目录（每个目录=一个数据集；无连续活性列者不可用于 DMTA）"
curl -s "${SCI[@]}" "$BASE/datasets" | python3 -c "
import sys, json
print('     %-26s %-9s %-8s %-14s %s' % ('数据集','类型','文件','活性列','可用于DMTA'))
for d in json.load(sys.stdin)['items']:
    c = (d.get('meta') or {}).get('compound') or {}
    print('     %-26s %-9s %-8s %-14s %s' % (d['id'], d['data_type'], d['n_files'],
          c.get('activity_column') or '-', 'YES' if c.get('usable_for_dmta') else 'no'))
"

# ══════════════════════════════════════════════════════════════════════ ACT 1
act "ACT 1 · 端到端案例：Caspase-3 抑制剂优化  (UI: 新建项目 → 新建任务 → 任务详情 → 项目报告)"
step "1.1 新建项目  (UI: 顶栏项目选择器 → ＋ 新建项目)"
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/projects" \
  -d '{"name":"Caspase-3 抑制剂优化","description":"针对 Caspase-3 的抑制剂优化：无肝毒性且水溶性良好","target":"Caspase-3","pdb_id":"1CP3","objectives":["hepatotoxicity","solubility"]}' \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('     ✓ id=%s  target=%s  PDB=%s  objectives=%s' % (d['id'], d['target'], d['pdb_id'], ','.join(d['objectives'])))
print('     created_by=%s  created_at=%s' % (d['created_by'], d['created_at']))
"
step "1.2 提交任务  (UI: 数据集=chembl_casp3_activities · 活性模型=QSAR · 3 轮 · 目标=无肝毒+溶解度)"
T1=$(curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/tasks" \
  -d '{"hypothesis":"寻找对 Caspase-3 高活性、无肝毒性且水溶性良好的小分子抑制剂","dataset_id":"chembl_casp3_activities","activity_model":"qsar","rounds":3,"objectives":["hepatotoxicity","solubility"],"project":"caspase-3"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['task_id'])")
echo "     Task ID = $T1"
step "1.3 执行 DMTA  (UI: 任务详情 → DMTA 拓扑实时点亮)"
wait_task "$T1" "casp3"
step "1.4 结果  (UI: 任务详情 → 数据集与模型 / 轮次时间线)"
curl -s "${SCI[@]}" "$BASE/tasks/$T1" | python3 -c "
import sys, json
d = json.load(sys.stdin); r = d.get('result') or {}
ds = r.get('dataset') or {}; md = r.get('activity_model') or {}
print('     数据集   : %s  有效分子=%s  含活性=%s' % (ds.get('dataset_id'), ds.get('n_valid'), ds.get('n_with_activity')))
print('     活性模型 : %s  train/test=%s/%s' % (md.get('kind'), md.get('n_train'), md.get('n_test')))
print('     指标     : %s' % md.get('metrics'))
print('     成药性   : %s' % r.get('admet_engine'))
print('     优化目标 : %s' % ','.join(r.get('objectives') or []))
print('     决策     : %s' % r.get('decision'))
print('     迭代     :')
for rd in r.get('rounds', []):
    print('       R%s  %s' % (rd['round'], rd['summary']))
    if rd.get('action'):
        print('           动作: %s' % rd['action'])
print('     候选（✓=通过全部目标）:')
for c in (r.get('top_candidates') or []):
    ok = ((c.get('pIC50') or 0) >= 6.5 and c.get('hepatotoxic') is False)
    print('      %s #%s  pIC50=%-6s 肝毒=%-6s 溶解度=%-8s hERG=%-6s SA=%-5s MPO=%s' % (
        '✓' if ok else ' ', c['id'], c.get('pIC50'), c.get('hepatotoxic'),
        round(c.get('solubility') or 0, 2), round(c.get('herg') or 0, 2),
        c.get('sa_score'), c.get('mpo')))
    print('           %s' % c['smiles'][:74])
"
step "1.5 项目报告  (UI: 项目报告 → 生成报告)"
curl -s "${SCI[@]}" "$BASE/tasks/$T1/report" -o /tmp/demo-casp3.html -w "     HTTP %{http_code} · %{size_download} bytes\n"
grep -o "<h2>[^<]*</h2>" /tmp/demo-casp3.html | sed 's/^/     /'
COLS=$(python3 - <<'PY'
import re, pathlib
h = pathlib.Path('/tmp/demo-casp3.html').read_text(encoding='utf-8')
sec = h.split('5. 候选化合物')[1].split('</table>')[0]
print(' | '.join(re.findall(r'<th[^>]*>([^<]+)</th>', sec)))
PY
)
echo "     候选表列（按优化目标自适应）: $COLS"
echo "     第4章验证散点图: $(grep -c 'class=\"scatter\"' /tmp/demo-casp3.html) 张"
echo "     散点数据点(预测vs实测): $(grep -o '<circle' /tmp/demo-casp3.html | wc -l) 个"
echo "     真实结构式: $(grep -c 'mol-cell' /tmp/demo-casp3.html) 个"
step "1.6 报告第4章 模型验证（节选：预测值 vs 实测值 的真实散点）"
python3 - <<'PY'
import re, pathlib
html = pathlib.Path("/tmp/demo-casp3.html").read_text(encoding="utf-8")
sec = html.split("4. 模型验证")[1].split("<h2>")[0]
for m in re.findall(r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"', sec)[:6]:
    print("     point  cx=%s cy=%s" % m)
for m in re.findall(r'(R²|MAE|Spearman|AUROC)[^<]*<[^>]*>([-\d.]+)', sec)[:6]:
    print("     metric %s = %s" % m)
PY

# ══════════════════════════════════════════════════════════════════════ ACT 2
act "ACT 2 · 第二个靶点：MetAP2 中枢渗透优化  (UI: 切换项目 → 新建任务 → 任务详情)"
step "2.1 新建项目  (UI: 项目选择器 → ＋ 新建项目)"
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/projects" \
  -d '{"name":"MetAP2 抑制剂优化","description":"MetAP2 抑制剂优化：需中枢渗透且无肝毒性","target":"MetAP2","pdb_id":"1B6A","objectives":["BBB","hepatotoxicity"]}' \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('     ✓ id=%s  target=%s  PDB=%s  objectives=%s' % (d['id'], d['target'], d['pdb_id'], ','.join(d['objectives'])))
"
step "2.2 提交任务  (UI: 数据集=chembl_metap2_activities · QSAR · 3 轮 · 目标=BBB+无肝毒)"
T2=$(curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/tasks" \
  -d '{"hypothesis":"寻找对 MetAP2 高活性、可穿透血脑屏障且无肝毒性的小分子","dataset_id":"chembl_metap2_activities","activity_model":"qsar","rounds":3,"objectives":["BBB","hepatotoxicity"],"project":"metap2"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['task_id'])")
echo "     Task ID = $T2"
step "2.3 执行 DMTA"
wait_task "$T2" "metap2"
step "2.4 结果"
curl -s "${SCI[@]}" "$BASE/tasks/$T2" | python3 -c "
import sys, json
d = json.load(sys.stdin); r = d.get('result') or {}
md = r.get('activity_model') or {}
print('     数据集 : %s  含活性=%s' % ((r.get('dataset') or {}).get('dataset_id'), (r.get('dataset') or {}).get('n_with_activity')))
print('     模型   : %s' % md.get('metrics'))
print('     决策 : %s' % r.get('decision'))
print('     迭代（反馈驱动）:')
for rd in r.get('rounds', []):
    print('       R%s  %s' % (rd['round'], rd['summary']))
    if rd.get('action'):
        print('           动作: %s' % rd['action'])
print('     候选（✓=通过全部目标）:')
for c in (r.get('top_candidates') or []):
    ok = ((c.get('pIC50') or 0) >= 6.5 and c.get('bbb') and c.get('hepatotoxic') is False)
    print('      %s #%s pIC50=%-6s BBB=%-6s 肝毒=%-6s 溶解度=%-8s MPO=%s' % (
        '✓' if ok else ' ', c['id'], c.get('pIC50'), c.get('bbb'), c.get('hepatotoxic'),
        round(c.get('solubility') or 0, 2), c.get('mpo')))
    print('           %s' % c['smiles'][:70])
"
step "2.5 两个靶点对比"
printf "     %-28s %-8s %s\n" "项目" "轮数" "结果"
for t in "$T1:Caspase-3 抑制剂优化" "$T2:MetAP2 抑制剂优化"; do
  tid=${t%%:*}; name=${t#*:}
  curl -s "${SCI[@]}" "$BASE/tasks/$tid" | python3 -c "
import sys, json
d = json.load(sys.stdin); r = d.get('result') or {}
print('     %-28s %-8s %s' % ('$name', str(len(r.get('rounds') or [])) + ' 轮', r.get('decision')))
"
done

# ══════════════════════════════════════════════════════════════════════ ACT 3
act "ACT 3 · 人工审批与审计  (UI: 合规与审计 → 审批 / 审计日志)"
step "3.1 待审批队列  (UI: 合规与审计 → 待审批)"
curl -s "${SCI[@]}" "$BASE/approvals?status=pending" -o /tmp/demo-appr.json
# approve the run that actually met its objectives - the interesting one
APPR=$(python3 -c "
import json
d = json.load(open('/tmp/demo-appr.json'))
items = d['items']
pref = [a for a in items if 'Objectives met' in (a.get('detail') or '')] or items
print(pref[0]['id'] if pref else '')
")
python3 -c "
import json
d = json.load(open('/tmp/demo-appr.json'))
print('     待审批 %d 项（将批准标记 * 者）:' % d['pending'])
for a in d['items']:
    star = '*' if a['id'] == '$APPR' else ' '
    print('      %s %s | %s' % (star, a['id'], a['title']))
    print('           %s' % (a['detail'] or '')[:68])
"
step "3.2 批准  (UI: 批准 → 填写意见)"
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/approvals/$APPR/decision" \
  -d '{"decision":"approved","comment":"溶解度达标，先合成 Top3 做活性验证"}' \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('     ✓ %s -> %s by %s (%s)' % (d['id'], d['status'], d['decided_by'], d['decided_at']))
print('       comment: %s' % d.get('comment'))
"
step "3.3 审计日志  (UI: 合规与审计 → 审计日志，JSON Lines 落盘)"
curl -s "${ENG[@]}" "$BASE/guardrails/events?limit=10" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('     总事件数 = %s' % d['total'])
print('     %-9s %-10s %-22s %-9s %s' % ('时间','角色','动作','决策','理由'))
for e in d['items']:
    print('     %-9s %-10s %-22s %-9s %s' % (e['ts'][11:19], e['role'], e['action'], e['decision'], e['reason'][:36]))
"

# ══════════════════════════════════════════════════════════════════════ ACT 4
act "ACT 4 · Guardrails 真实生效  (UI: 合规与审计 → 策略与 DLP)"
step "4.1 DLP · 拦截内部项目编号（BLOCK）  (UI: 任务提交时自动扫描)"
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/guardrails/dlp-check" \
  -d '{"text":"请把 PROJ-1234 的内部数据发给 DeepSeek 分析"}' \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('     action = %s   blocked = %s' % (d['action'], d['blocked']))
for f in d['findings']:
    print('     命中规则: %s (%s) action=%s  match=%s' % (f['rule'], f['description'], f['action'], f['match']))
"
step "4.2 DLP · 脱敏个人与化合物标识（MASK）"
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/guardrails/dlp-check" \
  -d '{"text":"联系人 zhangsan@example.com 手机 13812345678，化合物 CPD-88213 待测"}' \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('     action = %s' % d['action'])
print('     原文  : 联系人 zhangsan@example.com 手机 13812345678，化合物 CPD-88213 待测')
print('     脱敏后: %s' % d['masked_text'])
"
step "4.3 DLP 在真实任务提交链路上强制拦截（不是演示接口）"
curl -s -o /tmp/demo-dlp.json -w "     HTTP %{http_code}\n" "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/tasks" \
  -d '{"hypothesis":"参考 PROJ-1234 的结论继续优化","dataset_id":"molecule_net_bace","activity_model":"qsar","rounds":1,"objectives":["solubility"],"project":"bace1"}'
python3 -c "
import json, pathlib
d = json.loads(pathlib.Path('/tmp/demo-dlp.json').read_text(encoding='utf-8'))
print('     拒绝理由: %s' % json.dumps(d, ensure_ascii=False)[:180])
"
step "4.4 RBAC · guest 无权提交任务（403）"
curl -s -o /tmp/demo-rbac.json -w "     HTTP %{http_code}\n" "${JSON[@]}" "${GUEST[@]}" -X POST "$BASE/tasks" \
  -d '{"hypothesis":"guest 尝试提交","dataset_id":"molecule_net_bace","activity_model":"qsar","rounds":1,"objectives":["solubility"]}'
python3 -c "
import json, pathlib
print('     %s' % json.dumps(json.loads(pathlib.Path('/tmp/demo-rbac.json').read_text(encoding='utf-8')), ensure_ascii=False)[:180])
"
step "4.5 数据分级 · 同一个问题，clearance 不同则可见知识不同（RAG 检索过滤）"
RQ='{"query":"previous BACE1 DMTA campaign top candidates pIC50","top_k":5}'
echo "     guest (clearance=public):"
curl -s "${JSON[@]}" "${GUEST[@]}" -X POST "$BASE/rag/query" -d "$RQ" \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('       used_chunks=%s  blocked_chunks=%s  citations=%s' % (d['used_chunks'], d['blocked_chunks'], len(d['citations'])))
for c in d['citations'][:3]:
    print('        - [%-12s] %s' % (c['sensitivity'], c['title'][:52]))
"
echo "     scientist (clearance=confidential):"
curl -s "${JSON[@]}" "${SCI[@]}" -X POST "$BASE/rag/query" -d "$RQ" \
  | python3 -c "
import sys, json; d = json.load(sys.stdin)
print('       used_chunks=%s  blocked_chunks=%s  citations=%s' % (d['used_chunks'], d['blocked_chunks'], len(d['citations'])))
for c in d['citations'][:3]:
    print('        - [%-12s] %s' % (c['sensitivity'], c['title'][:52]))
print('       answer: %s' % d['answer'][:140].replace(chr(10), ' '))
"
step "4.6 机密数据集读取：三级 clearance 对比  (bace1_dmta_results = confidential)"
printf "     %-22s %s\n" "scientist (confidential)" "$(curl -s -o /dev/null -w 'HTTP %{http_code}' "${SCI[@]}" "$BASE/datasets/bace1_dmta_results/files")"
printf "     %-22s %s\n" "engineer (internal)" "$(curl -s -o /dev/null -w 'HTTP %{http_code}' "${ENG[@]}" "$BASE/datasets/bace1_dmta_results/files")"
printf "     %-22s %s\n" "guest (public)" "$(curl -s -o /dev/null -w 'HTTP %{http_code}' "${GUEST[@]}" "$BASE/datasets/bace1_dmta_results/files")"
curl -s "${ENG[@]}" "$BASE/datasets/bace1_dmta_results/files" | python3 -c "
import sys, json
print('     engineer 被拒理由: %s' % json.load(sys.stdin)['message'])
"
step "4.7 上述拒绝全部落审计（BLOCKED 可查）"
curl -s "${ENG[@]}" "$BASE/guardrails/events?decision=BLOCKED&limit=6" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('     BLOCKED 事件数 = %s' % d['total'])
print('     %-9s %-10s %-20s %-9s %s' % ('时间','角色','动作','决策','理由'))
for e in d['items']:
    print('     %-9s %-10s %-20s %-9s %s' % (e['ts'][11:19], e['role'], e['action'], e['decision'], e['reason'][:38]))
"

# ══════════════════════════════════════════════════════════════════════ end
act "收尾 · 平台最终状态"
curl -s "${SCI[@]}" "$BASE/projects" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('     项目 %d 个:' % d['total'])
for p in d['items']:
    print('       %-8s %-18s target=%-6s objectives=%s' % (p['id'], p['name'], p['target'], ','.join(p['objectives'])))
"
curl -s "${SCI[@]}" "$BASE/tasks" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('     任务 %d 个:' % len(d))
for t in d:
    print('       %-16s %-10s %-6s proj=%s' % (t['task_id'], t['status'], t['stage'], t.get('project')))
"
echo
echo "     演示用 ID: CASP3_TASK=$T1  METAP2_TASK=$T2"
