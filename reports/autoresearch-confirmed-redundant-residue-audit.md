# Autoresearch 完全冗余历史残留审计

> 审计时间：2026-07-20 14:45:29 +08:00  
> 审计性质：只读调查与本地文档交付  
> 当前结论：本文列出的对象在功能上可删除，但本文**不是清理授权**。本次没有删除、移动、覆盖或修改任何被审计对象。

> 后续实施更新（2026-07-20）：用户随后明确授权清理。第 12 节记录了实施结果；上面的“本次不删”仍是原始审计快照，不再代表当前现场状态。

## 1. 判定口径

本文只把同时满足下列条件的对象列入“确认冗余”清单：

1. 对当前受支持的 autoresearch 执行路径没有必要作用；
2. 不承载唯一源码、配置、指标、checkpoint 或实验结论；
3. 文件枚举与活动入口反向引用没有发现有效消费者，或内容能够无损再生成；
4. 服务器对象还必须没有活动进程、调度任务或已注册 Git worktree 引用；
5. 删除后有明确恢复方法。

以下两种情况不因“旧”或“重复”而进入删除清单：

- 仍承担发布、部署、恢复、审计或复现职责；
- 仍被配置、doctor、README、wrapper、测试或部署流程引用。

“功能上可删除”与“当前允许删除”是两个不同结论。PMT-SR A2/A3 保护门解除前，服务器对象、autoresearch run history 及其目录均禁止清理。

## 2. 当前保护状态与审计边界

### 2.1 服务器与训练快照

- 服务器工作树：`/home/cgv841/ybj`
- 服务器 commit：`cdd173fbd3c7146f98d39338556a66d64be62f30`
- PMT-SR A2 主进程 PID：`1587117`
- PMT-SR A3 主进程 PID：`1587123`
- 审计时两组主进程及其 DataLoader 子进程仍存在。
- 审计时未发现 `autoresearch_v2`、`run_autoresearch_*` 或旧手工 bridge 的活动进程。
- 未执行 `nvidia-smi`、GPU 探针、训练测试或 lease 操作。

PID 仅记录本次快照，未来不得直接用作终止或清理目标。清理前必须重新核对进程身份。

### 2.2 只读检查方法

本次使用了以下相互独立的证据面：

- 本地文件名与目录枚举；
- SHA-256 和逐字节重复检查；
- 从 PowerShell wrapper、配置、policy、README、tests 和部署脚本反向搜索引用；
- 服务器 `ps` 活动进程检查；
- 用户 crontab 和 user systemd unit 的相关名称检查；
- 服务器 state/history 中的引用检查；
- `git worktree list --porcelain` 与实际 worktree 目录内容对照；
- 本地 canonical source 与服务器部署文件对照。

一次无界服务器递归 grep 因超时中止，未修改任何状态；结论使用后续有界扫描重新取得，扫描范围限定为 `bin`、autoresearch 状态根、配置/入口和调度信息。

## 3. 已确认冗余对象总表

| 编号 | 对象 | 数量/大小 | 功能判定 | 当前是否允许删除 |
|---|---|---:|---|---|
| R-01 | 本地活动源码/测试生成的 `__pycache__` | 3 个目录、11 个 `.pyc`、184,298 字节 | 可再生成，无运行时唯一信息 | 本次不删；不受服务器训练依赖，但仍需单独清理操作 |
| R-02 | 历史 inspect 快照内的 `.pyc` | 2 个文件、24,375 字节 | 可由对应 Python 源码再生成 | **禁止当前删除**；位于受保护 run history |
| R-03 | 本地 collected artifact 中的空 `run_output` | 6 个空目录 | 零内容，不承载产物 | **禁止当前删除**；位于受保护 run history |
| R-04 | 服务器 autoresearch worktree 根下的空残留目录 | 17 个目录、0 个文件；目录树占用 73,728 字节 | 未注册 Git worktree，无进程引用 | **禁止当前删除**；须等待 A2/A3 保护门解除并复查 |
| R-05 | 服务器孤立的旧 bounded-training 脚本 | 2 个文件 | 无本地 canonical、无当前入口/调度/进程引用 | **禁止当前删除**；须先做完整哈希归档并复查 |

## 4. R-01：本地活动路径中的 Python 字节码缓存

### 4.1 精确清单

`C:\Users\pbrii\Desktop\科研\.agents\skills\codex-autoresearch-v2\scripts\__pycache__\`

- `autoresearch_v2_contracts.cpython-313.pyc` — 7,919 字节

`C:\Users\pbrii\Desktop\科研\scripts\remote\remote-bin\__pycache__\`

- `autoresearch_v2_common.cpython-313.pyc` — 22,909 字节
- `autoresearch_v2_driver.cpython-313.pyc` — 52,813 字节
- `autoresearch_v2_gpu_lease.cpython-313.pyc` — 4,857 字节
- `autoresearch_v2_metric_tvilfm.cpython-313.pyc` — 6,199 字节

`C:\Users\pbrii\Desktop\科研\tests\__pycache__\`

- `test_autoresearch_v2_contracts.cpython-313-pytest-8.4.2.pyc` — 6,496 字节
- `test_autoresearch_v2_modes.cpython-313-pytest-8.4.2.pyc` — 9,658 字节
- `test_autoresearch_v2_package_parity.cpython-313-pytest-8.4.2.pyc` — 3,066 字节
- `test_autoresearch_v2_project_contract.cpython-313-pytest-8.4.2.pyc` — 6,383 字节
- `test_remote_autoresearch_v2.cpython-313-pytest-8.4.2.pyc` — 40,225 字节
- `test_remote_autoresearch_v2_wrapper.cpython-313-pytest-8.4.2.pyc` — 23,773 字节

### 4.2 证据与处置条件

- 这些目录已被 Git ignore，不属于 tracked source。
- `.pyc` 是 CPython/pytest 根据 `.py` 自动生成的缓存，不是 canonical implementation。
- 删除不会改变源码、测试定义、plugin 或服务器部署。
- 恢复方式：再次导入相应模块或运行相应测试时由 Python 自动生成。

本报告不执行删除。未来清理应以明确的三个目录为目标，禁止用 workspace 根上的递归通配删除。

## 5. R-02：历史 inspect 快照内的字节码缓存

精确文件：

- `autoresearch-runs/stageb-token-aware-pa05-r3/inspect/w1/TVI-LFM/scripts/__pycache__/run_stage_b_token_aware_pa05_ablation.cpython-313.pyc` — 11,096 字节
- `autoresearch-runs/stageb-token-aware-pa05-r3/inspect/w1/TVI-LFM/scripts/__pycache__/smoke_stage_b_token_aware_pa05.cpython-313.pyc` — 13,279 字节

判定依据：

- 两个文件都是 Python 字节码缓存，对应源文件仍存在于同一 inspect 快照；
- autoresearch runtime、状态文件和 metrics 不引用 `.pyc`；
- 它们不构成实验指标、配置、源码文本或 checkpoint。

限制与恢复：

- 它们虽然功能上冗余，但位于历史 run snapshot 中，当前历史保留政策优先，**不得随 R-01 一并清理**；
- 若未来明确批准精简历史快照，先记录文件 SHA-256 和父目录清单，再删除；
- 必要时可用对应 Python 版本从源文件再生成，但生成后的字节码哈希不保证与旧解释器产物一致，因此恢复以事先归档为准。

## 6. R-03：本地 collected artifact 内的空目录

以下六个目录均为空：

- `autoresearch-runs/fdgap-e4-20260713b/collected/artifacts/w1/iter-0001/run_output/`
- `autoresearch-runs/fdgap-h1-20260713b/collected/artifacts/w1/iter-0001/run_output/`
- `autoresearch-runs/v2-smoke-20260707-211948/collected/artifacts/w1/iter-0001/run_output/`
- `autoresearch-runs/v2-smoke-20260707-213327/collected/artifacts/w1/iter-0001/run_output/`
- `autoresearch-runs/v2-smoke-20260707-214604/collected/artifacts/w1/iter-0001/run_output/`
- `autoresearch-runs/v2-smoke-20260707-220901/collected/artifacts/w1/iter-0001/run_output/`

判定依据：目录内没有文件、链接或子目录，不承载结果，也不是当前 runtime 的工作目录。删除空目录不会改变同级的 `command.json`、`outcome.json`、`process.log` 或 `results/metrics.json`。

限制与恢复：它们仍处于受保护的历史 collected 树，本次及 A2/A3 保护期内不删除。恢复只需在原路径重新创建空目录。

## 7. R-04：服务器空 worktree 目录残留

根目录：`/home/cgv841/ybj/autoresearch-v2/worktrees/`

审计结果：

- 17 个一级目录；
- 整棵目录树中普通文件数为 0；
- `du -sb` 为 73,728 字节，均为目录结构开销；
- `git -C /home/cgv841/ybj worktree list --porcelain` 没有注册其中任何目录；
- Git 当前只注册主工作树 `/home/cgv841/ybj` 和独立的 `/home/cgv841/worktrees/ybj-h1-hpt-stage1`；后者不在本清单中；
- 审计时无 autoresearch 进程引用这些目录。

空目录清单：

- `external-screen-20260714`
- `external-screen-20260714b`
- `external-screen-full-20260714b`
- `external-screen-verify-20260714`
- `fdgap-e4-20260713a`
- `fdgap-e4-20260713b`
- `fdgap-h1-20260713a`
- `fdgap-h1-20260713b`
- `stageb-token-aware-pa05`
- `stageb-token-aware-pa05-r3`
- `stageb-token-aware-pa05-r4`
- `stageb-token-aware-pa05-r5`
- `stageb-token-aware-pa05-r6`
- `v2-smoke-20260707-211948`
- `v2-smoke-20260707-213327`
- `v2-smoke-20260707-214604`
- `v2-smoke-20260707-220901`

删除前必须重新满足：

1. A2/A3 联合保护门已解除；
2. 无 autoresearch 进程；
3. 每个目标仍为空；
4. `git worktree list --porcelain` 仍不注册目标；
5. 目标解析后的绝对路径仍严格位于 `/home/cgv841/ybj/autoresearch-v2/worktrees/` 下。

恢复方式：这些目录不含数据，未来 bootstrap/worker 创建流程可按需重新创建。不得触碰 `/home/cgv841/worktrees/ybj-h1-hpt-stage1`。

## 8. R-05：服务器孤立的旧 autoresearch 脚本

### 8.1 精确对象与哈希

| 路径 | SHA-256 |
|---|---|
| `/home/cgv841/ybj/bin/run_autoresearch_train.sh` | `810342d62ecb8c3673c3ff23dbdd874be63a39b069ab38ec4b7a049ca211b38f` |
| `/home/cgv841/ybj/bin/run_autoresearch_trial.sh` | `8b3bb50cf5a9cf66edbd7f13da39f3067259b2316290ea0527a2bd1bc2f08fcb` |

### 8.2 冗余证据

- 本地 `scripts/remote/remote-bin/` 中没有同名 canonical source；
- 当前 `deploy-remote-bin.ps1` 只上传本地 `remote-bin/*.sh`，因此不会部署或恢复这两个服务器独有文件；
- 当前 v2 bridge、driver、plugin、policy、README 和本地 wrapper 没有以它们作为入口；
- 当前 `remote.local.psd1` 指向的是 `run_train.sh`、`run_smoke_test.sh`、`check_job.sh` 和 `cancel_job.sh`，不指向这两个文件；
- 审计时没有对应活动进程；
- 用户 crontab 和 user systemd unit 未发现对应调度引用；
- 历史 experiment JSON 中仍可能出现脚本名，但这些只是不可执行的历史字符串记录，不是当前入口。

### 8.3 删除前条件与恢复

在保护门解除后仍必须重新执行：活动进程检查、调度检查、当前树引用检查和 state 引用分类。随后：

1. 记录路径、权限、所有者、大小、mtime 和完整 SHA-256；
2. 把两个文件原样归档到独立、不可执行的 hash archive；
3. 验证归档文件哈希与上表及删除前现场哈希一致；
4. 仅删除这两个精确路径，不对 `/home/cgv841/ybj/bin/` 使用通配或递归删除。

恢复方式：从 hash archive 原样还原路径和权限，再核对 SHA-256。由于本地没有 canonical source，不得假设 Git checkout 能恢复它们。

## 9. 检查过但不可删除的对象

### 9.1 重复但仍承担职责

- 本地 canonical 与 `plugins/codex-autoresearch-v2/` 中有 26 个逐字节相同文件。plugin 是版本化发布形态，当前不能删除；未来应改为从唯一 canonical source 生成并验证，而不是手工双份维护。
- 服务器 `autoresearch_v2_common.py`、`autoresearch_v2_driver.py`、`autoresearch_v2_gpu_lease.py`、`autoresearch_v2_metric_tvilfm.py` 和 `run_autoresearch_v2_bridge.sh` 与本地对应文件哈希一致。这证明部署一致，不证明服务器副本冗余。

### 9.2 已退出活动发现但必须保留

- `.agents/audit/codex-autoresearch-legacy/` 不在 `.agents/skills/` 活动发现路径中，但它是旧实现的审计快照；删除会丢失历史设计证据。
- Git refs/logs、历史 results、metrics、状态、日志、experiment 输出和 checkpoint 用于追溯或复现，不进入清理清单。

### 9.3 看似旧但仍可达

以下本地/服务器手工链仍被配置、doctor、README、wrapper、测试或部署流程引用，不能判为完全冗余：

- `run_train.sh`
- `run_smoke_test.sh`
- `check_job.sh`
- `cancel_job.sh`
- `researchops_common.sh`
- `run_mbpatch_light_ablation_bridge.sh`
- `run_sampling_mining_ablation_bridge.sh`
- 对应的 PowerShell submit/check/cancel wrappers
- `config/autoresearch-train.example.psd1`
- `config/autoresearch-train.local.psd1`
- `config/remote.example.psd1`
- `config/remote.local.psd1`

它们可以在未来通用化后进入“退役候选”，但必须先移除活动引用、替代手工能力并重新审计，不能依据本文直接删除。

### 9.4 活动控制与历史状态

以下对象均不进入删除清单：

- `.agents/skills/codex-autoresearch-v2-dev/`：被 policy、invoke skill 和测试明确引用；
- program、targets、policy 和 tests：分别承担实验输入、权限边界和回归保护；
- `autoresearch-runs/`、服务器 runs、uploads、分支和非空结果：承担状态、恢复或历史证据；
- `leases/.lock`：虽然可再生成，但它是有效协调机制，不按历史残留处理；
- PMT-SR、TVI-LFM、数据、配置、checkpoint、outputs 和 Python 环境：不属于本次冗余清理范围。

## 10. 清理授权门槛

本文不授予删除权限。任何服务器或 run-history 清理必须在以下条件全部满足后另行批准：

- [ ] A2/A3 主进程及全部 DataLoader 子进程不存在；
- [ ] 两组均有明确终态和完整日志；
- [ ] 最后 checkpoint、metrics、配置和源码 commit 已记录哈希；
- [ ] `nvidia-smi` 中不存在对应训练 PID；
- [ ] PMT-SR 输出不再持续更新；
- [ ] 本文所有“无引用”“为空”和哈希结论已现场复核；
- [ ] 服务器脚本归档已完成并通过哈希验证；
- [ ] 删除目标解析后的绝对路径逐项核对，不使用宽泛递归模式。

## 11. 本阶段交付声明

本阶段只新增本文档。未执行：

- 本地缓存、空目录或历史产物清理；
- 服务器文件或目录删除、移动、覆盖、chmod 或归档；
- Git checkout、切换、提交、部署或 bridge 更新；
- autoresearch tests、CPU fixture、GPU 检查或训练命令；
- lease、run state、uploads、worktrees、PMT-SR 配置、checkpoint 或 outputs 修改。

后续通用化实施必须先阅读本文，并以实施当时重新取得的只读证据为准；不得把 2026-07-20 的快照直接转换成删除命令。

## 12. 后续授权实施记录

实施前重新核对了唯一活动训练 `a3_e4_hpt_l025` 的父进程、训练主进程、DataLoader 子进程、GPU PID、打开日志和输出目录，并将该进程树及其 TVI-LFM 源码、配置、输入 checkpoint、数据和 Python 环境列为冻结边界。

- R-01：活动源码和测试缓存已清除；最终验证后再次清除测试生成的精确缓存目录。
- R-02：删除历史 inspect 快照中的 2 个 `.pyc`，共 24,375 字节；对应源码仍保留。
- R-03：删除 6 个经复核仍为空的 `run_output` 目录。
- R-04：17 个服务器空 worktree 残留此前已删除；实施后根目录仍为空。
- R-05：两个孤立脚本原样归档至 `/home/cgv841/ybj/archives/autoresearch-legacy-bin-20260720/`，归档哈希验证后删除原路径。

非活动实验另行归档至：

`/home/cgv841/ybj/archives/ybj_inactive_experiments_20260720T2233/`

该归档包含 64 个实验根、4,504 个元数据文件、逐文件 SHA-256、155,953,714 字节的 `metadata.tar.gz`、52 个 checkpoint 路径到 50 个内容寻址 blob 的映射，以及 5 个中间快照的完整哈希记录。`cleanup.json` 记录了后续删除、硬链接去重和空间变化。清理共删除 5 个中间 checkpoint（5,287,539,689 字节）、去重 1 个 checkpoint 路径、移除 17 个已完整归档的 dry-run/audit 目录；实际可用空间增加 6,346,498,048 字节。

legacy audit、历史 autoresearch runs、主要实验结果、best/latest checkpoint、发布 plugin 和服务器 staging 均继续保留。

### 12.1 最终复核（2026-07-20 23:42 +08:00）

- R-01 的三个精确 `__pycache__` 目标均已不存在；最终测试使用 `PYTHONDONTWRITEBYTECODE=1`，清理后未再运行会生成字节码的测试。
- R-02 的两个历史 `.pyc` 与 R-03 的六个空 `run_output` 均保持已删除状态。
- R-04 根目录 `/home/cgv841/ybj/autoresearch-v2/worktrees/` 当前零条目。
- R-05 两个活动路径均不存在；归档副本 SHA-256 分别为 `810342d62ecb8c3673c3ff23dbdd874be63a39b069ab38ec4b7a049ca211b38f` 与 `8b3bb50cf5a9cf66edbd7f13da39f3067259b2316290ea0527a2bd1bc2f08fcb`，与删除前记录一致。
- 非活动实验归档当前无 `.partial` 残留；`metadata.tar.gz` 仍为 155,953,714 字节，SHA-256 为 `7b035a09177077d71c304bff32b9f54a3a0f430bc19b9d7fc653d085506e20fa`，与 manifest 一致。
- 唯一活动训练仍为父 PID `2087629`、GPU 主 PID `2087809` 及其 DataLoader 子进程；`nvidia-smi` 仅报告 PID `2087809` 为 compute process。未发现 autoresearch 进程。

## 13. 后续全量旧版本清理

2026-07-21 用户进一步授权清除旧版本历史产物。因此本文此前列为“保留”的 legacy audit、旧服务器 runtime/script 归档、旧 run state 和旧 refs 已在重新核验后清除；研究实验归档、结果和当前 schema-v2 实现继续保留。完整记录见 `reports/autoresearch-old-version-full-purge-20260721.md`。
