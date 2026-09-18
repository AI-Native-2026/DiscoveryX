# DiscoveryX — 演示指南

一份 15–20 分钟的端到端演示动线，覆盖从建项目到出报告、再到安全护栏的完整链路。

> 本文所有数字均为在参考部署上实跑所得，可用 `scripts/remote/demo_run.sh` 一键复现。
> 任务 / 审批 ID 每次运行都会重新生成；其余指标（分子数、模型指标、候选 pIC50、
> 拦截计数）是确定性输出。

---

## 0. 准备

| 项 | 值 |
|---|---|
| 前端 | http://43.135.120.107:8080 |
| API 文档 | http://43.135.120.107:8000/docs |
| 健康检查 | `curl http://43.135.120.107:8000/api/v1/health` |
| 初始状态 | 0 个项目、0 个任务、0 条审批（平台不预置任何演示数据） |

一键重置并跑完整流程（清空项目 / 任务 / 审批，保留数据集）：

```bash
python scripts/vm_ssh.py --timeout 1500 --script scripts/remote/demo_run.sh
```

服务由 systemd 托管，崩溃自动重启、开机自启：

```bash
systemctl status discoveryx-api discoveryx-worker
```

---

## 演示动线总览

| 幕 | 内容 | 时长 |
|---|---|---|
| ACT 0 | 平台就绪 + 数据集目录 | 1 min |
| ACT 1 | **端到端案例**：Caspase-3 抑制剂优化 | 6 min |
| ACT 2 | **第二个靶点**：MetAP2 中枢渗透优化 | 4 min |
| ACT 3 | 人工审批 + 审计 | 3 min |
| ACT 4 | 安全护栏：RBAC / DLP / 数据分级 | 5 min |

---

## ACT 0 · 平台就绪（1 min）

**UI**：打开 http://43.135.120.107:8080 （默认深色、中文）

1. **侧边栏**：折叠 / 展开，图标保留、仅文字收起
2. **顶栏语言切换**：中 / 英一键切换，全站 16 个页面即时生效
3. **系统状态页**：Redis / LLM / Chroma 三项全绿

**API 对照**（`GET /health`）：

```
app=DiscoveryX v0.1.0  env=development
redis ok   llm configured   chroma ok
```

4. **数据与知识 → 数据目录**：9 个数据集，全部来自真实公开数据源

| 数据集 | 类型 | 活性列 | 可用于 DMTA |
|---|---|---|---|
| `chembl_casp3_activities` | tabular | `pchembl_value` | ✓ |
| `chembl_metap2_activities` | tabular | `pchembl_value` | ✓ |
| `chembl_egfr_activities` | tabular | `pchembl_value` | ✓ |
| `chembl_ache_activities` | tabular | `pchembl_value` | ✓ |
| `molecule_net_bace` | tabular | `pIC50` | ✓ |
| `pdb_bace1_structures` | structure | – | ✗ |
| `pmc_bace1_literature` | document | – | ✗ |
| `bace1_dmta_results` | document | – | ✗ |
| `AAA` | document | – | ✗ |

**讲解要点**：
> 平台初始 0 个项目——数据集是平台级共享的公共资源，项目里不预置任何运行结果。
> 每个目录就是一个数据集；**没有连续活性列（pIC50 / IC50）的目录会被 422 拒绝建任务**，
> 因为没法定量建模。这里 4 个不可用的目录正是被这条规则挡住的。

---

## ACT 1 · 端到端案例：Caspase-3 抑制剂优化（6 min）

### 1.1 新建项目

**UI**：顶栏项目选择器 → `＋ 新建项目`

| 字段 | 值 |
|---|---|
| 名称 | `Caspase-3 抑制剂优化` |
| 靶点 | `Caspase-3` |
| PDB | `1CP3` |
| 目标 | 勾选 `无肝毒性` + `溶解度` |
| 描述 | 针对 Caspase-3 的抑制剂优化：无肝毒性且水溶性良好 |

```
✓ id=caspase-3  target=Caspase-3  PDB=1CP3  objectives=hepatotoxicity,solubility
```

> 项目 = 靶点 + PDB 结构 + 优化目标 + 数据边界。同名项目会自动生成唯一 id
> （`caspase-3` → `caspase-3-2`），不会因重名失败。

### 1.2 提交任务

**UI**：任务列表 → `新建任务`

| 字段 | 值 |
|---|---|
| 假设 | 寻找对 Caspase-3 高活性、无肝毒性且水溶性良好的小分子抑制剂 |
| 数据集 | `chembl_casp3_activities` |
| 活性模型 | `QSAR`（LightGBM，用该数据集现场训练） |
| 迭代轮数 | `3` |

```
Task ID = task-642558b8
```

> 迭代轮数指的是 **DMTA 迭代轮数**，不是重试次数。重试是独立配置
> （ARQ `max_tries=2`），且 `GuardrailViolation` 永不重试——安全拒绝是确定性的。

### 1.3 执行

**UI**：任务详情 → DMTA 拓扑实时点亮

```
[casp3] succeeded done 1/3 100%
```

> 只跑了 **1 轮就收敛**——目标达成即停，未达成才继续迭代，这是成本控制。

### 1.4 结果

```
数据集   : chembl_casp3_activities  有效分子=1694  含活性=1694
活性模型 : qsar  train/test=1345/349
指标     : r2=0.4277  mae=0.6718  spearman=0.648  auroc_binarised=0.8476
成药性   : admet_ai
优化目标 : hepatotoxicity, solubility
决策     : Objectives met - candidates are ready for synthesis and assay.
迭代     : R1  round 1: 8 candidates, 5 passed all objectives
           动作: 从数据集高活性分子出发，枚举类似物；已剔除 2 个数据集已知化合物
```

候选（✓ = 通过全部目标）：

| # | pIC50 | 无肝毒 | 溶解度 logS | hERG | SA | MPO |
|---|---|---|---|---|---|---|
| 1 | 9.04 | ✓ | −2.68 | 0.08 | 3.78 | 0.717 |
| 2 | 7.52 | ✓ | −3.58 | 0.54 | 4.30 | 0.572 |
| 3 | 7.52 | ✓ | −3.26 | 0.53 | 4.27 | 0.572 |
| 4 | 7.47 | ✓ | −3.44 | 0.50 | 4.32 | 0.567 |
| 5 | 7.42 | ✓ | −3.32 | 0.50 | 4.33 | 0.562 |

**讲解要点**：
> - 活性模型是用这个数据集**现场训练**的（1345 训练 / 349 测试，scaffold split，
>   即测试集骨架与训练集不重叠），不是加载一个泛化模型。
> - ADMET 用 ADMET-AI 的预训练 Chemprop 模型（DILI / hERG / BBB / 溶解度等），
>   零训练、CPU 可跑。
> - **候选保证是数据集之外的新分子**：数据集里的实测化合物只作为设计起点，
>   不会作为"设计产物"报回来；动作里会明确标注剔除了几个已知化合物。
>   这避免了把已知活性物当作新发现这种循环论证。
> - 数据准备阶段做了清洗：只保留未删失（`=`）的 nM 级 IC50，并把同一分子多次
>   测定的 pIC50 取**中位数**收敛为一个标签。原始 ChEMBL 导出中同一分子最多有
>   4.6 个 log 单位的测定分歧，直接训练会让标签自相矛盾。

### 1.5 报告

**UI**：项目报告 → `生成报告`

```
HTTP 200 · 157310 bytes
1. 摘要与决策   2. 数据与模型   3. 迭代过程（反馈驱动）   4. 模型验证
5. 候选化合物（含结构式）   6. 成药性与多参数评分
7. 证据与引用   8. 成本与运行清单

候选表列（按优化目标自适应）: # | 结构 | SMILES | pIC50 | 无肝毒 | 溶解度 logS | SA | QED | 路线步数 | MPO
第4章验证散点图: 1 张   散点数据点: 200 个   真实结构式: 6 个
```

**UI**：滚动到**第 4 章 模型验证** → 预测值 vs 实测值散点图（含 y=x 参考线）

**讲解要点**：
> 报告只对**本次真正优化的端点**显示达标与否。这个项目没有 BBB 目标，所以报告
> 里不会出现 BBB 列——不会把一个与项目无关的指标渲染成"失败"。顶部还有一行
> "优化目标：无肝毒性 / 溶解度"的标记。
>
> 第 4 章的散点图是 QSAR 在**留出测试集**上的真实预测 vs 实测，每点一个分子，
> 不是示意图。第 5 章的结构式由 RDKit 现场渲染为 SVG。报告是自包含的浅色文档，
> 可直接用浏览器打印成 PDF。

---

## ACT 2 · 第二个靶点：MetAP2 中枢渗透优化（4 min）

展示同一引擎在**不同靶点、不同目标组合**下的表现。

### 2.1–2.2 切换项目并建任务

**UI**：项目选择器 → `＋ 新建项目` → 名称 `MetAP2 抑制剂优化`、靶点 `MetAP2`、
PDB `1B6A`、目标勾选 `血脑屏障渗透` + `无肝毒性`
→ 任务列表 `新建任务` → 数据集 `chembl_metap2_activities`、QSAR、3 轮

```
Task ID = task-1f29597a
```

### 2.3–2.4 执行与结果

```
[metap2] succeeded done 1/3 100%

数据集 : chembl_metap2_activities  含活性=915
模型   : r2=0.297  mae=0.4316  spearman=0.5397  auroc_binarised=0.7625
决策   : Objectives met - candidates are ready for synthesis and assay.
迭代   : R1  round 1: 4 candidates, 4 passed all objectives
```

候选（✓ = 通过全部目标）：

| # | pIC50 | BBB | 无肝毒 | 溶解度 logS | MPO |
|---|---|---|---|---|---|
| 1 | 8.56 | ✓ | ✓ | −3.02 | 0.842 |
| 2 | 8.11 | ✓ | ✓ | −2.23 | 0.793 |
| 3 | 7.19 | ✓ | ✓ | −3.95 | 0.710 |
| 4 | 6.90 | ✓ | ✓ | −2.97 | 0.681 |

### 2.5 两个靶点对比

| 项目 | 轮数 | 结果 |
|---|---|---|
| Caspase-3 抑制剂优化 | 1 轮 | Objectives met |
| MetAP2 抑制剂优化 | 1 轮 | Objectives met |

**讲解要点**：
> 两个靶点用**同一个引擎**，目标组合不同（一个是无肝毒+溶解度，一个是 BBB+无肝毒），
> 都收敛到达标候选。
>
> 迭代是**反馈驱动**的：若某轮目标未达成，平台会识别失败原因（如"氢键供体过多"），
> 在下一轮施加针对性化学修饰（甲基化羟基/伯胺等），而不是随机重试。
> 目标在给定轮次内未全部达成时，平台如实标注并给出优化方向，不会为了报告好看而
> 放宽判定。判定标准：候选必须 `pIC50 ≥ 6.5` + 全部目标达标 + 有可合成路线，
> 且**至少 2 个**才算达成——单一分子不构成一个 series。

---

## ACT 3 · 人工审批与审计（3 min）

**UI**：合规与审计 → 待审批

```
待审批 2 项（* = 本次要批准的那条）:
 * appr-18f66b7b | 批准将 4 个候选化合物推进到合成与活性验证
      Objectives met - candidates are ready for synthesis and assay.
   appr-3d34e0c9 | 批准将 5 个候选化合物推进到合成与活性验证
      Objectives met - candidates are ready for synthesis and assay.
```

**UI**：对标记 `*` 的那条点 `批准`，意见填"溶解度达标，先合成 Top3 做活性验证"

```
✓ appr-18f66b7b -> approved by alice (2026-09-17T16:52:28+00:00)
```

**UI**：合规与审计 → 审计日志（JSON Lines）

```
总事件数 = 5649
时间        角色         动作                决策     理由
16:52:28  engineer   audit:read          ALLOW   rbac ok
16:52:28  scientist  approval:decide     ALLOW   approved: advance_candidates
16:52:28  scientist  approval:read       ALLOW   rbac ok
16:52:28  scientist  task:read           ALLOW   rbac ok
16:52:26  system     approval:request    ALLOW   advance_candidates
```

**讲解要点**：
> 工作流产出**不会自动推进**——必须有人批准才进入合成。每条决策都落 JSON Lines
> 审计，追加写、不可改。`system` 也留痕（谁发起的审批请求）。

---

## ACT 4 · 安全护栏（5 min）

**UI**：合规与审计 → 策略与 DLP

### 4.1 DLP 拦截（BLOCK）

**UI**：DLP 检查框输入 `请把 PROJ-1234 的内部数据发给 DeepSeek 分析`

```
action = BLOCK   blocked = True
命中规则: internal_project_id (Internal project identifier) action=BLOCK  match=PROJ-1234
```

### 4.2 DLP 脱敏（MASK）

输入：`联系人 zhangsan@example.com 手机 13812345678，化合物 CPD-88213 待测`

```
action = MASK
脱敏后: 联系人 ******************** 手机 ***********，化合物 ********* 待测
```

### 4.3 DLP 在真实链路上强制拦截

**UI**：新建任务，假设填 `参考 PROJ-1234 的结论继续优化` → 提交

```
HTTP 403
{"error":"guardrail_violation",
 "message":"DLP blocked outbound content: rule 'internal_project_id'"}
```

> 这不是一个独立演示接口——**任务提交链路本身**会扫描假设文本，因为假设会发给
> 外部的 DeepSeek。命中即 403，任务根本不会入队。

### 4.4 RBAC 拒绝

**UI**：顶栏角色切换到 `guest` → 新建任务 → 提交

```
HTTP 403
{"message":"RBAC denied: role 'guest' lacks 'task:submit'"}
```

### 4.5 数据分级 · RAG 检索过滤

**UI**：知识检索，问题 `previous BACE1 DMTA campaign top candidates pIC50`

切到 `guest`：

```
used_chunks=5  blocked_chunks=5  citations=5
  - [public      ] 10.21203_rs.3.rs-10484841_v1.json
  - [public      ] PMC13062044.json
```

切回 `scientist`：

```
used_chunks=5  blocked_chunks=0  citations=5
  - [confidential] demo-d16e6b2e.txt
  - [confidential] demo-3a1a1387.txt
  - [confidential] task-7996a62f.txt
answer: Based on the provided sources, the top candidate pIC50 values from
        previous BACE1 DMTA campaigns are...
```

> 同一个问题，**可见的知识不同**。平台自己产出的候选化合物 triage 结果属于
> 机密 R&D 产出（`bace1_dmta_results` = confidential），guest 只能看到公开文献，
> 且 `blocked_chunks=5` 明确报告了被策略拦下的块数。

### 4.6 机密数据集读取 · 三级对比

```
scientist (confidential) HTTP 200
engineer  (internal)     HTTP 403   RBAC denied: clearance 'internal' < 'confidential'
guest     (public)       HTTP 403   RBAC denied: role 'guest' lacks 'dataset:read'
```

### 4.7 拒绝全部留痕

```
BLOCKED 事件数 = 5668
16:52:38  engineer   data:read      BLOCKED  insufficient clearance for confidential
16:52:38  guest      dataset:read   BLOCKED  missing permission dataset:read
16:52:36  guest      rag:filter     BLOCKED  clearance filter dropped 5 chunk(s)
16:52:29  guest      task:submit    BLOCKED  missing permission task:submit
16:52:29  scientist  task:submit    BLOCKED  DLP:internal_project_id
```

> 每一次拒绝都留痕，包括被 DLP 拦下的科学家操作。审计日志是 append-only 的
> JSON Lines，可以直接接入 SIEM。
>
> 权限设计上，`dataset:index` 属于 engineer，但机密数据集只有 `admin`
> （restricted clearance）能索引——索引操作需要 `dataset:index` **且** clearance
> 达标，这是最小权限原则。

---

## 设计说明 FAQ

**为什么 ADMET 用预训练模型，活性模型却现场训练？**
> ADMET 有成熟的公开预训练模型（ADMET-AI / Chemprop，覆盖 DILI、hERG、BBB、
> 溶解度等），泛化好、零训练成本，CPU 就能跑。而**靶点活性高度依赖具体靶点**，
> 泛化模型没有意义，必须用项目自己的数据现场训练，并用 scaffold split 做诚实的
> 留出评估。这也是为什么没有活性列的数据集会被 422 拒绝。

**LLM 用在哪？会不会编造数值？**
> LLM 只用在两处：把检索到的文献证据**总结**成摘要，以及生成定向修饰的建议文案。
> 所有数值（pIC50、ADMET、溶解度、SA、MPO）都来自确定性计算，LLM 不参与打分。
> RAG 的 prompt 明确要求"只依据提供的来源作答，不足则说明不足"。

**为什么候选必须"相对数据集是新的"？**
> 数据集的实测化合物是设计**起点**。如果把已知活性物直接当成设计产物报回来，
> 结论就是循环论证，而且会掩盖模型的真实泛化能力。因此候选生成后会与数据集
> 做规范化 SMILES 比对，已知分子一律剔除，并在动作说明中标注剔除数量。

**为什么报告不显示与项目无关的端点？**
> 目标由项目定义。一个非中枢靶点项目把 BBB 渲染成"失败"是误导。因此任务状态和
> 报告都携带 `objectives`，前端表格与报告候选表只对目标端点显示达标与否，
> 其余端点作为信息列或完全不显示。

**前端为什么不用 Streamlit？**
> 企业级平台需要 API-First、前后端分离、可嵌入企业门户、可做细粒度前端权限。
> Streamlit 是数据科学原型工具，这些做不到。

**任务队列为什么选 ARQ 而不是 Celery？**
> 整个后端是 asyncio 原生的 FastAPI。ARQ 是 asyncio 原生的 Redis 队列，与事件
> 循环同构，无需跨进程模型；Celery 是同步 / 多进程模型，在这个栈里是额外的阻抗
> 不匹配。代价是 ARQ 生态较小，但它足够稳定，且我们完全掌控重试语义。

---

## 运维提示

| 情况 | 处理 |
|---|---|
| worker 未运行 | `sudo systemctl restart discoveryx-worker` |
| 任务长时间停留在 queued | 同上；worker 启动时会自动清理残留的 `arq:in-progress` 键 |
| LLM 调用失败 | RAG 会降级为抽取式回答；DMTA 的数值计算不依赖 LLM |
| 前端资源异常 | 硬刷新（Ctrl+Shift+R）；静态资源带 hash 指纹 |
| 需要完全重置 | 跑 `scripts/remote/demo_run.sh`（自带重置） |
| 查看平台状态 | `scripts/remote/final_check.sh` |

---

## 附：可复现命令

```bash
# 完整演示（自动重置 + 全流程 + 实测输出）
python scripts/vm_ssh.py --timeout 1500 --script scripts/remote/demo_run.sh

# 平台状态速查（项目 / 任务 / 项目隔离）
python scripts/vm_ssh.py --script scripts/remote/final_check.sh

# 后端质量门禁（ruff + pytest）
python scripts/vm_ssh.py --script scripts/remote/backend_test.sh

# 单独跑某个靶点（数据集 · 靶点名 · PDB · 目标 · 项目名）
python scripts/vm_ssh.py --put scripts/remote/try_target.sh /home/ubuntu/try_target.sh
python scripts/vm_ssh.py "bash /home/ubuntu/try_target.sh \
  chembl_casp3_activities Caspase-3 1CP3 '[\"hepatotoxicity\",\"solubility\"]' 'Caspase-3 抑制剂优化'"
```

本文对应那一次运行的产物：

```
CASP3_TASK  = task-642558b8   报告: /api/v1/tasks/task-642558b8/report
METAP2_TASK = task-1f29597a   报告: /api/v1/tasks/task-1f29597a/report
APPROVED    = appr-18f66b7b
```
