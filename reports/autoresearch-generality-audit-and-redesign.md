# Autoresearch 通用化审计与安全重构方案

> 审计日期：2026-07-20  
> 当前状态：**仅完成本地审计文档；未修改代码、服务器部署、训练配置或运行状态。**  
> 生效约束：PMT-SR A2/A3 仍在训练，本文中的重构操作全部推迟到训练保护门解除后。

> 后续实施更新（2026-07-20）：原 A2/A3 已结束；实施时服务器存在另一条唯一活动流水线 `a3_e4_hpt_l025`。重构在新的冻结边界外完成。第 10 节记录最终实施与验证结果；本文前面的“尚未执行”是原始方案快照。

## 1. 结论摘要

当前 autoresearch v2 的基础控制模型是可复用的：Git worktree 隔离、候选改动 keep/discard、单一主指标、失败回滚、sealed mode，以及可选 GPU lease 都应保留。

通用性下降主要来自两类耦合：

1. **活动 runtime/skill 直接理解 TVI-LFM、SYSU、PMT 和 Stage A 的训练语义**，包括配置改写、日志解析、指标名、checkpoint/epoch/CUDA provenance 和专用 smoke/self-check。
2. **同一实现同时存在于活动 workspace、打包 plugin 和服务器副本中**，且部分版本或行为已发生漂移，增加了错误部署和漏改的风险。

建议采用不兼容的新 target `schema_version: 2`：runtime 原样执行 target 声明的 argv，只规定运行目录、预算、可选 GPU 和统一结果文件协议；项目侧命令自行完成配置展开、日志解析及训练专属 provenance。旧 schema 对新启动明确返回 `unsupported-schema`，不在新 runtime 中保留启动兼容层。

这项设计**不会要求删除历史实验资料**。legacy audit、旧 run state、训练结果、checkpoint、上传、worktree 和 lease 记录均保留。需要从活动核心中移除的是项目专用执行逻辑，而不是历史证据。

## 2. 当前训练保护边界

### 2.1 审计时观测快照

- 服务器工作树：`/home/cgv841/ybj`
- 审计时源码 commit：`cdd173fbd3c7146f98d39338556a66d64be62f30`
- A2 主进程 PID：`1587117`
- A3 主进程 PID：`1587123`
- 两组命令均从 `/home/cgv841/ybj/PMT-SYSU` 启动，使用 `/home/cgv841/anaconda3/envs/reid/bin/python -m pmt_sysu.train ...`
- 审计时仍存在相应 DataLoader 子进程，日志和输出仍在更新。
- 未发现 autoresearch driver/bridge 是 A2/A3 的父进程；当前训练直接依赖 PMT-SYSU 目录、配置、环境和输出路径。

PID 只用于记录本次审计观测，不可作为未来终止或清理目标；解除保护时必须重新识别进程及其命令行。

### 2.2 保护期间允许与禁止的操作

在 A2/A3 全部终止前，只允许：

- 读取服务器状态；
- 在本地编写和审阅本报告。

禁止：

- 修改、切换、更新或清理 `/home/cgv841/ybj` Git 工作树；
- 触碰 `PMT-SYSU/`、超分派生数据、outputs、checkpoint、训练配置或 Python 环境；
- 部署、覆盖、重命名或删除 `/home/cgv841/ybj/bin/` 中的脚本；
- 清理 autoresearch worktree、lease、run state、uploads 或历史产物；
- 运行可能申请 GPU、创建训练进程或改变 GPU lease 的测试；
- 以旧 PID 为依据发送终止信号或执行清理。

### 2.3 解除保护的联合门槛

以下条件必须同时满足并留存证据：

- [ ] A2、A3 主进程及其 DataLoader/派生子进程均不存在；
- [ ] A2、A3 均有明确终态记录和完整日志；
- [ ] 两组最后 checkpoint、metrics、展开后的配置及源码 commit 已记录哈希；
- [ ] `nvidia-smi` 中不存在对应训练 PID；
- [ ] PMT-SR 输出在约定观察窗口内不再持续更新。

建议将解除保护的检查结果写入单独的只读证据清单，由人工确认后再开始下文的实现阶段。

## 3. Autoresearch 实现与状态的完整位置清单

以下清单按“活动实现、打包镜像、项目控制面、测试、服务器部署、历史实现、非代码状态”区分，避免把历史结果误判为活动代码，也避免只检查 skill 而漏掉 runtime。

### 3.1 本地活动 skill 与 runtime

| 类别 | 位置 | 角色 |
|---|---|---|
| 活动 skill | `C:\Users\pbrii\Desktop\科研\.agents\skills\codex-autoresearch-v2\` | 用户面向的工作流、契约说明、validator |
| 开发 skill | `C:\Users\pbrii\Desktop\科研\.agents\skills\codex-autoresearch-v2-dev\` | 开发模式辅助入口 |
| Skill 主说明 | `.agents/skills/codex-autoresearch-v2/SKILL.md` | v2 使用流程与约束 |
| Skill 元数据 | `.agents/skills/codex-autoresearch-v2/agents/openai.yaml` | skill 展示/调用元数据 |
| Skill references | `.agents/skills/codex-autoresearch-v2/references/` | mode、program、target、keep/discard、recovery、parallel-workers、logging/curve 契约 |
| Skill validators | `.agents/skills/codex-autoresearch-v2/scripts/` | program/target validator 与公共 contracts |
| 本地入口 | `scripts/remote/autoresearch-v2.ps1` | v2 控制入口 |
| 模式守卫 | `scripts/remote/guard-autoresearch-mode.ps1` | 模式校验 |
| 专用 smoke | `scripts/remote/smoke-autoresearch-v2.ps1` | 当前包含项目/阶段专用检查 |
| PowerShell 库 | `scripts/remote/lib/` | common、ssh、paths、result、autoresearch_v2 等控制逻辑 |
| Python runtime | `scripts/remote/remote-bin/autoresearch_v2_*.py` | driver、common、GPU lease、TVI-LFM metric parser、mode guard |
| Linux bridge | `scripts/remote/remote-bin/run_autoresearch_v2_bridge.sh` | 服务器侧桥接入口 |

### 3.2 打包 plugin 镜像

完整打包副本位于：

`C:\Users\pbrii\Desktop\科研\plugins\codex-autoresearch-v2\`

它包含 skill 和 runtime 的镜像。审计时核心源文件与活动 workspace 对应文件哈希一致，但人工双份维护本身仍是结构性风险。plugin manifest 标记为 `0.1.3`，readonly contract 仍断言 `0.1.2`，已形成可观察的版本漂移。

后续应确定唯一 canonical source，并由可验证的打包流程生成 plugin；不得继续把两个目录当作可独立修改的源码源头。

### 3.3 项目控制面

| 位置 | 内容 |
|---|---|
| `autoresearch/program*.md` | 实验 program 定义 |
| `autoresearch/targets/*.yaml` | target 定义，包括项目命令、路径和可变范围 |
| `config/autoresearch-v2.example.psd1` 及其他 autoresearch 配置 | 本地/远程控制配置 |
| `.codex/research-policy.json` | 研究策略与权限边界 |
| `.githooks/pre-commit` | 提交约束 |

具体项目的命令、工作目录、输入、产物和指标方向应继续由 target 表达；它们不是因为“具体”就属于过度设计。问题只发生在这些知识被写进通用 runtime 或通用自检时。

### 3.4 测试实现

当前相关测试包括：

- `tests/test_autoresearch_v2_contracts.py`
- mode 相关测试；
- package parity 测试；
- project contract 测试；
- remote autoresearch v2 测试；
- wrapper 测试；
- remote proxy contract 测试。

既有审计运行结果为 `33 passed, 3 failed, 1 teardown error`。已知问题包括：plugin/contract 版本不一致、项目检查失败，以及 Windows 后台 status/log handle 测试问题。这些结果只作为重构基线记录；保护期间不重新运行可能进入远程或 GPU 路径的测试。

### 3.5 服务器部署副本

活动 v2 部署位于 `/home/cgv841/ybj/bin/`：

- `autoresearch_v2_common.py`
- `autoresearch_v2_driver.py`
- `autoresearch_v2_gpu_lease.py`
- `autoresearch_v2_metric_tvilfm.py`
- `run_autoresearch_v2_bridge.sh`

审计时下列四个 Python 文件与本地 canonical 候选副本一致：

| 文件 | SHA-256 前缀/记录 |
|---|---|
| `autoresearch_v2_driver.py` | `50bfcabc...` |
| `autoresearch_v2_common.py` | `55ffd4ea...` |
| `autoresearch_v2_metric_tvilfm.py` | `8ea1b6ed...` |
| `autoresearch_v2_gpu_lease.py` | `060567a5...` |

服务器 `/home/cgv841/ybj/bin/` 还存在旧或残留入口：

- `cancel_job.sh`
- `check_job.sh`
- `researchops_common.sh`
- `run_autoresearch_train.sh`
- `run_autoresearch_trial.sh`
- `run_mbpatch_light_ablation_bridge.sh`
- `run_sampling_mining_ablation_bridge.sh`
- `run_smoke_test.sh`
- `run_train.sh`

审计时未发现当前 `state.json` 引用这些旧 bridge，也未发现其活动进程。但这不足以授权立即删除：必须在训练结束后重新检查引用，先生成完整哈希归档，再清除确定无引用的“活动副本”。

### 3.6 本地 legacy/历史实现

- `.agents/audit/codex-autoresearch-legacy/`：完整旧 skill、脚本、测试和文档的审计归档；保留。
- `scripts/remote/remote-bin/researchops_common.sh`
- `scripts/remote/remote-bin/run_train.sh`
- `scripts/remote/remote-bin/run_smoke_test.sh`
- `scripts/remote/remote-bin/run_mbpatch_light_ablation_bridge.sh`
- `scripts/remote/remote-bin/run_sampling_mining_ablation_bridge.sh`
- 与上述入口对应的 PowerShell submit/check/cancel/manual wrappers。

`run_autoresearch_train.sh` 和 `run_autoresearch_trial.sh` 审计时只在服务器发现，本地当前源码树中没有对应源文件，应视为部署残留候选，而不是从记忆推断其来源。

### 3.7 非代码运行状态与历史产物

以下内容不属于待“通用化”的源码，默认全部保留：

- 本地 `autoresearch-runs/`；
- 服务器 `/home/cgv841/ybj/autoresearch-v2/runs/`；
- uploads；
- worktrees；
- leases；
- state、events、历史日志和实验结果；
- 远程 autoresearch 分支；
- REID/PMT-SR 数据、配置、checkpoint 和 outputs；
- `.agents/audit/codex-autoresearch-legacy/`。

审计未发现 `autoresearch/generated` 中存在需要纳入活动实现的内容，也未发现 canonical/plugin 之外的同名 v2 runtime 副本。

## 4. 过度设计裁决

### 4.1 从通用核心删除

| 设计 | 证据/表现 | 裁决 | 通用替代 |
|---|---|---|---|
| TVI-LFM 专用 parser | `autoresearch_v2_metric_tvilfm.py` 理解 TVI 日志、Rank-1/mAP/mINP，并固定选择 mAP | 从活动核心和 plugin 删除 | 项目命令写统一 `metrics.json` |
| Driver 的 `tvilfm_reid` 分支 | driver 导入专用 parser，并借 parser 类型触发配置准备 | 删除 | runtime 不理解 parser 类型或项目配置 |
| Stage A 默认 target/config | PowerShell 库和配置默认到 `tvilfm-stage-a.yaml` | 删除默认值 | 新启动必须显式指定 schema v2 target |
| 项目专用 smoke | smoke 固定 TVI Stage A 文件、路径和 clipreid Python | 从通用包移出 | 通用 CPU fixture；项目 smoke 留在项目侧 |
| 自检中的项目断言 | local checks 断言 TVI-LFM/Stage A root/path | 删除 | 只检查 schema、路径边界、命令可执行性和结果协议 |

删除的含义是“从未来活动核心移除”，不是现在删除文件，也不是抹除 Git 历史或 legacy audit。

### 4.2 改为 target 配置

以下信息合理但不应由 runtime 猜测或硬编码：

| 信息 | schema v2 归属 |
|---|---|
| 命令及参数 | `run.argv`，字符串数组，原样执行 |
| 工作目录 | `run.cwd`，相对 target repo |
| 环境变量 | `run.env`，显式 mapping；敏感值仅允许引用受控注入，不写进事件 |
| 时间预算 | `run.budget_minutes` |
| 结果文件 | 固定目录协议 `$AR2_RESULTS_DIR/metrics.json` |
| 主指标方向/门槛 | `metric.direction` 与可选 policy |
| 产物 | `artifacts` 相对路径或 glob，强制路径包含检查 |
| 输入哈希 | `provenance.inputs` 显式声明 |
| GPU | `gpu.mode: none|lease` 及可选约束 |

target 中出现某个项目名或项目命令是正常职责边界；通用 plugin/runtime 不得复制这些项目知识。

### 4.3 泛化固定的训练语义

| 当前固定语义 | 问题 | 泛化设计 |
|---|---|---|
| Rank-1/mAP/mINP 必需 | 限定 ReID 指标体系 | 只要求有限数值 `primary_metric`；其他指标为不透明 mapping |
| 指标限制在 `[0,1]` | 排除 loss、时间、分数和百分制指标 | 仅检查 JSON number 且为有限值 |
| epoch/checkpoint 必需 | 把所有任务假设为 epoch 训练 | 作为项目可选 artifact/provenance |
| train/eval 固定事件 | 把事件模型绑定训练循环 | 核心只发通用生命周期事件；项目自定义事件保持 opaque |
| CUDA/GPU 必需 | 排除 CPU 任务 | GPU lease 完全可选，CPU 是一级模式 |
| dataset fingerprint 必需 | 输入不一定是 dataset | 改为任意声明输入及其哈希 |
| 固定 curve 布局 | 强制训练曲线存在 | 曲线作为可选 artifact，runtime 不解析 |
| TVI legacy log adapter | 通用核心承担项目兼容 | 移至项目命令或历史适配工具，不进入新 core |

### 4.4 保留的通用能力

下列能力解决的是实验自动化的普遍问题，不应因清除项目耦合而删除：

- Git branch/worktree 隔离；
- sealed mode 与允许修改路径边界；
- 候选变更 keep/discard；
- 单一标量主指标及 higher/lower 方向；
- 失败/超时回滚；
- append-only trial outcome/events；
- 可选 GPU lease；
- 命令超时、进程树回收与状态采集；
- 路径 containment、防止 artifact/input 逃逸；
- program、target 和 source snapshot/hash；
- baseline 与候选结果可追溯性。

### 4.5 历史保留而非清除

以下内容即使包含专用设计，也不应从历史中删除：

- legacy audit；
- 旧 run state、events 和日志；
- 已完成或在途实验的配置、checkpoint、metrics 和 outputs；
- 用于复现实验的源码 commit/branch/worktree 记录；
- 旧服务器脚本的哈希清单和归档副本。

因此，“过度设计”不等于“全部清除”。活动核心应去耦；项目 target 应配置化；历史证据应冻结保留。

## 5. Schema v2 通用接口

### 5.1 责任边界

Runtime 负责：

- 读取并验证 schema v2 target；
- 创建隔离 run/worktree/results 目录；
- 提供预算和可选 GPU lease；
- 原样执行 argv；
- 读取统一结果文件；
- 应用 keep/discard policy；
- 记录通用 provenance、状态和事件；
- 收集 target 声明的 artifacts。

项目命令负责：

- 生成或展开项目配置；
- 把 placeholder 转换成项目真正接受的参数；
- 解析项目日志；
- 选择主指标；
- 记录训练特有的配置、dataset、checkpoint、epoch 和曲线；
- 将最终结果写入统一 JSON。

Runtime **不得改写项目 YAML**，不得按项目名选择 parser，也不得从日志猜测结果。

### 5.2 Target 示例

以下是接口草案，不代表现在创建或启用该 target：

```yaml
schema_version: 2
name: example-cpu-target

repo:
  path: /path/to/repository

run:
  cwd: .
  argv:
    - python
    - tools/run_experiment.py
    - --results-dir
    - "${AR2_RESULTS_DIR}"
  env:
    EXAMPLE_MODE: baseline
  budget_minutes: 20

metric:
  path: metrics.json
  primary_key: primary_metric
  direction: higher

artifacts:
  - logs/**/*.log
  - outputs/summary.json

provenance:
  inputs:
    - configs/example.yaml
    - data/manifest.json

gpu:
  mode: none
```

约束：

- `schema_version` 必须严格等于整数 `2`；旧版或缺失版本返回明确的 `unsupported-schema`，不猜测升级。
- `run.argv` 必须是非空字符串数组，不经过 shell 字符串拼接，不由 runtime 添加项目参数。
- `run.cwd`、artifact 和 provenance input 必须在允许根目录内。
- runtime 只展开它自己拥有的通用占位符/环境值：worker root、run dir、run output dir、results dir、budget 和可选 GPU。
- `metric.path` 必须解析到 `$AR2_RESULTS_DIR` 内；v2 初始版本可只允许 `metrics.json`，减少多余自由度。
- `gpu.mode: none` 不申请 lease；`gpu.mode: lease` 才进入 GPU 调度。

建议由 runtime 提供下列环境变量，而非改写项目配置：

- `AR2_WORKER_ROOT`
- `AR2_RUN_DIR`
- `AR2_OUTPUT_DIR`
- `AR2_RESULTS_DIR`
- `AR2_BUDGET_MINUTES`
- `AR2_GPU_ID`（仅获得 lease 时存在）

### 5.3 统一结果文件

实验命令必须原子地写入：

`$AR2_RESULTS_DIR/metrics.json`

示例：

```json
{
  "primary_metric": 73.42,
  "metrics": {
    "accuracy": 73.42,
    "latency_ms": 18.7,
    "validation_loss": 0.284
  }
}
```

规则：

- `primary_metric` 必须存在，是 JSON number，且不是 NaN 或正负 Infinity；不限制到 `[0,1]`。
- `metrics` 可缺省；存在时为名称到有限数值的 mapping。
- runtime 不理解 `accuracy`、`mAP`、`loss` 等名称的含义。
- 缺失、格式错误、非有限值或写到 results 目录之外均导致明确失败，不从 stdout 猜测补救。
- 项目若需复杂报告、曲线或嵌套指标，应把它们声明为 artifacts，而不是扩张 core metric schema。

### 5.4 通用 provenance、status 与 events

Core provenance 仅记录：

- 实际 argv、cwd 和经过脱敏的环境摘要；
- program/target 内容及哈希；
- Git commit、dirty/source snapshot 状态；
- target 声明的输入及哈希；
- runtime/package 版本及哈希；
- 时间、退出码、超时/取消原因；
- `primary_metric`、可选 metrics 和所收集 artifacts 的哈希；
- GPU lease 摘要（仅实际使用时）。

核心事件限定为通用生命周期：

- `run_started`
- `metric_recorded`
- `artifact_recorded`
- `run_finished`

项目可以另写自定义事件或 artifact，runtime 将其视为不透明数据，不要求 epoch、checkpoint、train/eval 或曲线结构。

## 6. 安全实施与服务器切换方案

本节是训练保护解除后的实施顺序；目前不执行。

### 阶段 0：冻结和证据采集

1. 完成第 2.3 节联合门槛。
2. 记录 PMT-SR A2/A3 的源码 commit、配置、最后 checkpoint、metrics、日志和输出清单哈希。
3. 对 `/home/cgv841/ybj/bin/`、当前 runtime、plugin 和 canonical source 生成完整 SHA-256 manifest。
4. 记录当前 bridge 配置、状态引用和进程引用，不修改任何文件。

### 阶段 1：本地 generic runtime

1. 选定唯一 canonical source，版本提升到 `0.2.0`。
2. 新建 schema v2 validator，旧 schema 在 launch 前失败。
3. 删除 core 对 TVI-LFM parser、Stage A 默认、项目配置改写和训练专属 provenance 的依赖。
4. 实现 argv 原样执行、通用环境、`metrics.json` 读取、artifact/input containment 和可选 GPU。
5. 将项目适配命令留在各自 repository/target，不放入通用 skill/plugin。
6. 从 canonical source 可重复地生成 plugin，并用 hash/parity 测试阻止漂移。

### 阶段 2：纯 CPU fixture 验证

在临时 CPU Git repository 中验证：

- doctor 实际读取并检查显式指定 target；
- baseline；
- 指标改善后的 keep；
- 指标退化后的 discard；
- higher 与 lower 两种方向；
- 大于 1、负数等有限主指标；
- timeout 和完整进程树回收；
- collect 与 artifact 哈希；
- 缺失/非法 metrics 文件；
- artifact/input 路径逃逸拒绝；
- `gpu.mode: none` 不触发 GPU/lease；
- 旧 schema 返回 `unsupported-schema`。

fixture 不引用 TVI-LFM、SYSU、PMT、Stage A，不导入训练环境，不执行 SSH/GPU 申请。

### 阶段 3：服务器 staging

1. 将验证后的 runtime 部署到独立 staging 目录，例如 `/home/cgv841/ybj/autoresearch-v2-staging/<version>/`。
2. 不覆盖现有 `/home/cgv841/ybj/bin/`。
3. 比较 canonical、package、staging 的逐文件哈希。
4. 在服务器临时 CPU Git repo 复跑最小 fixture；明确设置无 GPU 模式。
5. 验证 staging 的 runs/worktrees/leases/root 与旧路径无交集。

### 阶段 4：原子切换

1. 再次确认没有活动 autoresearch/PMT-SR 进程引用旧 bridge/runtime。
2. 备份当前 bridge 指向和完整 hash manifest。
3. 通过单一原子入口切换到 staging；不得逐文件覆盖形成混合版本。
4. 运行只读 doctor 和 CPU canary。
5. 若失败，按已记录入口原子回滚；不回滚或改写历史 runs。

### 阶段 5：旧活动副本归档与清理

1. 对旧服务器脚本建立带 SHA-256、mtime、大小和原路径的归档。
2. 搜索配置、state、cron/service、shell history 可验证范围及活动进程引用。
3. 只清除确认无引用的 `/home/cgv841/ybj/bin/` 活动副本。
4. 不删除 legacy audit、历史 runs、PMT-SR 结果、uploads、worktrees 或 lease 历史。

“清理”不得与切换在同一步进行，应保留足够观察期和可回滚入口。

## 7. 对当前 PMT-SR 代码构建的影响判断

### 当前文档阶段

无影响。本阶段只新增本地 Markdown 文件，不触碰：

- `/home/cgv841/ybj` 工作树；
- `PMT-SYSU/`；
- A2/A3 配置、环境、checkpoint、日志或 outputs；
- 服务器 `bin/`；
- GPU lease 和训练进程。

### 未来重构阶段的主要风险

未来如果在 A2/A3 运行期间覆盖服务器 `bin/`、切换 Git 工作树、清理 worktree/lease，或把旧 schema 立即用于仍在运行/恢复的任务，确实可能破坏恢复链、状态采集或后续复现实验。因此实施被严格放在联合门槛之后，并采用 staging + CPU fixture + 原子切换。

通用化不会修改 PMT-SR 的训练源码本身。PMT-SR 若未来继续由 autoresearch 启动，需要在项目侧新增 schema v2 adapter/command：它负责准备 PMT 配置、执行训练并写通用 `metrics.json`。该 adapter 属于项目 target，而不是通用 core；它也不得回写或替换已完成 A2/A3 的配置和结果。

## 8. 验收标准

### 8.1 PMT-SR 不变性

- [ ] 重构前后 A2/A3 的源码 commit、配置、checkpoint、metrics、日志和结果文件哈希完全一致；
- [ ] 未改变 PMT-SYSU Python 环境；
- [ ] 未删除或重写 PMT-SR、超分派生数据和历史结果。

这里的“结果哈希完全不变”针对冻结时已存在的同一文件集合；应先记录清单，再比较，避免把后来新增的独立文件误报为篡改。

### 8.2 通用性

- [ ] 活动 generic skill/plugin/runtime 中不存在 `TVI-LFM`、`SYSU`、`PMT`、`Stage A` 硬编码；
- [ ] runtime 不解析项目日志，不改写项目 YAML；
- [ ] CPU target 是一级用例，GPU lease 为可选项；
- [ ] 指标名称不固定，`primary_metric` 只要求有限数值；
- [ ] epoch、checkpoint、curve、CUDA、dataset 均不是 core 必填字段。

对上述字符串的扫描应排除 legacy audit、迁移说明、测试负例和历史结果，否则会产生伪阳性；活动包和运行时必须为零命中。

### 8.3 行为与部署

- [ ] CPU fixture 的 doctor、baseline、keep/discard、timeout、collect 全部通过；
- [ ] fixture 不创建 GPU 或训练进程副作用；
- [ ] doctor 实际检查调用者指定的 target，而非默认或仅检查 controller；
- [ ] 旧 schema 返回明确 `unsupported-schema`；
- [ ] package、canonical source 与服务器 staging 哈希一致；
- [ ] staging 与旧 runs/worktrees/leases 路径无交集；
- [ ] 原子切换和原子回滚均经过 CPU canary 验证。

## 9. 本阶段交付与明确延期项

本阶段唯一交付物是本文档。

截至本文创建时，以下事项均**尚未执行**：

- 未修改 skill、runtime、plugin、target、policy 或测试；
- 未新增 schema v2 代码或 PMT-SR adapter；
- 未运行 CPU/GPU fixture；
- 未连接服务器进行部署、切换、归档或清理；
- 未更改 `/home/cgv841/ybj` Git 状态；
- 未清理任何 run state、worktree、lease、输出或历史产物。

下一次实施必须从第 2.3 节保护门复核开始，而不是直接进入代码修改。

## 10. 后续实施与验收记录

### 10.1 通用化实现

- runtime/package 版本提升到 `0.2.0`；target 严格要求整数 `schema_version: 2`。
- 旧 target 在 doctor/bootstrap 前返回明确 `unsupported-schema`，没有启动兼容层。
- runtime 原样执行 `run.argv`，只展开 runtime 拥有的 `AR2_*` 值，不再改写项目 YAML 或解析项目日志。
- 结果协议统一为 results 根内的 `metrics.json`；`primary_metric` 只要求有限 JSON number，可选 `metrics` 为名称到有限数值的 mapping。
- provenance 只记录 argv/cwd、program/target/runtime 哈希、Git/source 状态、声明输入、脱敏环境摘要、退出状态、指标和声明 artifact 哈希。
- 核心 events 仅保留 `run_started`、`metric_recorded`、`artifact_recorded` 和 `run_finished`。
- CPU 是一级模式；仅 `gpu.mode: lease` 才调用 lease，`none` 不查询或申请设备。
- 删除活动 core/package 中的 TVI-LFM metric parser、项目配置准备逻辑和训练曲线契约；专用 smoke 改为要求显式 program/target 的通用流程。
- canonical skill/runtime 与 versioned plugin 镜像通过逐字节 parity 测试。

### 10.2 本地 CPU 验证

29 项 autoresearch 回归测试全部通过，覆盖：

- 显式 target doctor；
- baseline、higher/lower、keep/discard；
- 大于 1 和负数主指标；
- 缺失/非法/非有限 metrics；
- artifact/input containment；
- provenance 与 artifact 哈希；
- timeout 完整进程树回收；
- `gpu.mode: none` 零 lease；
- 旧 schema 的 `unsupported-schema`；
- canonical/package parity、invoke/develop guard 和 plugin 结构验证。

`quick_validate.py` 与 `validate_plugin.py` 均通过。

### 10.3 服务器 staging、切换和清理

新 runtime 部署在独立目录：

`/home/cgv841/ybj/autoresearch-v2-staging/0.2.0/`

staging CPU fixture 完成 doctor、baseline、keep、discard、collect、timeout tree reaping 和旧 schema 拒绝，未创建 lease 文件。活动训练进程列表在 fixture 前后完全一致。

旧 runtime 在切换前归档至：

`/home/cgv841/ybj/archives/autoresearch-v2-runtime-pre-0.2.0-20260720/`

生产 bridge 经“新入口 canary → 原子回滚 → 旧入口 doctor → 再次原子切换 → 最终 canary”验证后，稳定指向 staging 的绝对入口。旧 `driver/common/gpu_lease/metric parser` 在哈希归档后从服务器 `bin/` 删除。生产 tracked Git 状态前后保持为同样的 3 个既有 TVI-LFM 修改，未新增或改写 tracked 文件。

### 10.4 活动训练不变性

实施前后活动流水线 PID 列表一致，训练主 PID `2087809` 始终是唯一 GPU compute PID。未修改其进程树、输出目录、配置、输入 checkpoint、派生数据、TVI-LFM Python 环境或现有 tracked TVI-LFM 文件。

### 10.5 最终验收复核（2026-07-20 23:42 +08:00）

- 本地最终测试：29 项通过；`quick_validate.py` 与 `validate_plugin.py` 通过。
- canonical、plugin 与服务器 staging 的四个 runtime 文件逐字节一致：`common c6d57245…`、`driver 10afa469…`、`gpu_lease 060567a5…`、`bridge ee951831…`。
- 活动 generic skill/plugin/runtime 对 `TVI-LFM`、`SYSU`、`PMT`、`Stage A`、`mAP`、`mINP`、旧 parser 名称及项目配置准备函数的定向扫描为零命中；迁移说明、legacy audit 和独立的旧项目 wrapper 不计入活动 generic core。
- 服务器最终 CPU fixture 再次通过 doctor、baseline、keep、discard、collect、timeout tree reaping 和旧 schema 拒绝；`lease_files=0`，活动训练进程列表前后完全一致。
- 生产 bridge 的显式 target doctor 通过，并确认读取 `/home/cgv841/ybj/autoresearch-v2-staging/0.2.0/cpu-fixture-final/target.yaml` 指定的仓库。
- 生产入口仍原子指向独立 staging；旧 `driver/common/gpu_lease/metric parser` 活动副本均不存在，切换前归档和 `switch-cleanup.json` 保留。
- 服务器 tracked 状态保持为实施前已有的三个 TVI-LFM 修改；唯一 compute PID 仍为 `2087809`，未发现残留 autoresearch 进程。

### 10.6 后续旧版本全量清理

2026-07-21 在新 runtime 验证稳定后，用户明确授权进一步清除旧版本历史产物。旧 rollback/script 归档、旧 schema runs/uploads、staging fixture/canary、旧 refs/tag、legacy audit 和旧项目输入均已删除；当前 `0.2.0/bin`、空 state 根、lease 协调机制、研究实验归档和训练结果保留。详见 `reports/autoresearch-old-version-full-purge-20260721.md`。
