# Autoresearch v2 正式错误报告与修复验收指南

> 审计日期：2026-07-11
> 审计对象：`origin/main`，提交 `f63e070`（Merge pull request #2）
> 审计方式：静态代码核对、现有本地测试、临时目录最小复现
> 本报告只记录问题与修复验收要求；审计期间没有修改 v2 runtime、训练配置、TVI-LFM 模型或训练算法，也没有连接真实 SSH/GPU。

## 1. 结论摘要

用户提供的错误报告核心判断大体属实，但不能原样作为修复说明。经核验：

| 项目 | 核验结论 | 说明 |
|---|---|---|
| 旧版活动技能隔离 | **属实，P0** | 当前 `main` 同时发现 `codex-autoresearch`、`codex-autoresearch-v2`、`codex-autoresearch-v2-dev`。旧 snapshot 已重新进入 `.agents/skills/`。 |
| PowerShell bridge 非零退出码传播 | **属实，P0，但范围需校正** | `baseline/run/resume/status/collect/stop/sync-best` 使用 `-AllowFailure`，写出 `ok=false` 后脚本仍退出 0。`doctor` 当前已经通过异常路径退出 1。 |
| bounded timeout 保留有效指标 | **属实，P0** | `TimeoutExpired` 进入通用异常路径，既不调用 metric parser，也不写 `results.tsv`。 |
| 失败 trial 审计日志 | **属实，P0** | 异常只更新 state 并写 `worker-failed` event，没有 crash 结果行；三类记录的关联字段也不一致。 |
| 异常后 PID/GPU lease 清理 | **原报告表述不准确** | `failed` 状态会清空 PID，GPU lease 在 `finally` 中释放；这两点已有实现，应保留并补回归测试。worker 中的 `gpu` 字段不会清空，语义仍可改进。 |
| baseline 与 retained best 保护 | **部分属实，P1** | 重复 baseline 会无条件 keep 并覆盖 `best_metric/best_commit/best_branch`，但 `baseline` 字段保持旧值，形成状态分裂。普通 run 的 threshold 判定和 discard 回滚已正确；crash 后未回滚到 best。 |
| v2 doctor | **属实，P1，但 PowerShell 部分需校正** | Python doctor 无条件 `ok=true`；即使找不到 Git 也退出 0。PowerShell doctor 对远端非零退出当前已能返回非零，应添加测试而不是重复修复。 |
| 现有测试覆盖 | **不足** | 当前 20 个相关测试全部通过，但没有覆盖以上失败语义，绿色测试不能证明运行时闭环正确。 |

除原报告外，还确认一个必须纳入正式修复的发布问题：`plugins/codex-autoresearch-v2/` 内包含 runtime 的版本化副本。根目录 runtime 与 plugin 副本当前字节一致；修复时必须同步修改并增加 parity 测试，否则本地源码修复后，可安装插件仍会保留旧缺陷。

## 2. 审计范围与现有测试基线

### 2.1 审计文件

- `.agents/skills/codex-autoresearch-v2/`
- `.agents/skills/codex-autoresearch-v2-dev/`
- `.agents/skills/codex-autoresearch/`
- `scripts/remote/autoresearch-v2.ps1`
- `scripts/remote/lib/autoresearch_v2.ps1`
- `scripts/remote/remote-bin/autoresearch_v2_driver.py`
- `scripts/remote/remote-bin/autoresearch_v2_common.py`
- `plugins/codex-autoresearch-v2/`
- `tests/test_autoresearch_v2_*.py`
- `tests/test_remote_autoresearch_v2.py`
- `tests/test_remote_autoresearch_v2_wrapper.py`

### 2.2 已执行的现有测试

```powershell
python -m unittest discover -s tests -p 'test_autoresearch_v2*.py' -v
python -m unittest discover -s tests -p 'test_remote_autoresearch_v2*.py' -v
```

结果：

- contract/mode/project 测试：14 项通过；
- driver/wrapper 测试：6 项通过；
- 合计：20 项通过。

这些测试覆盖了配置校验、mode guard、bootstrap、apply、正常 keep/discard、后台 start/stop/resume 和 wrapper 正常路径，但没有覆盖 bridge 非零传播、timeout、失败结果行、重复 baseline、crash 回滚和 doctor 失败。

## 3. 已确认缺陷

### AR2-P0-001：旧版 snapshot 重新成为活动技能

**严重级别：P0**
**状态：已复现**

当前技能发现目录包含：

```text
.agents/skills/codex-autoresearch/
.agents/skills/codex-autoresearch-v2/
.agents/skills/codex-autoresearch-v2-dev/
```

`.codex/research-policy.json` 虽然把 invoke/develop 指向 v2，但它不能阻止 Codex 从 `.agents/skills/codex-autoresearch/SKILL.md` 发现旧技能。旧目录还包含 background runtime、hooks、exec 和 foreground adapter 的完整实现与文档，会重新引入已经退出正式架构的入口和行为。

**所需修复：**

1. 从 `.agents/skills/` 删除 `codex-autoresearch`。
2. 如必须保留审计材料，原样移动到 `.agents/audit/codex-autoresearch-legacy/`；该目录不得被 skill discovery 扫描。
3. 正式活动 autoresearch skill 只保留：
   - `.agents/skills/codex-autoresearch-v2/`
   - `.agents/skills/codex-autoresearch-v2-dev/`
4. 不要从旧 snapshot 抽取 background、hooks、exec 或 foreground adapter 逻辑接入 v2。
5. 新增项目级测试，明确断言旧活动路径不存在；现有 mode policy 测试只检查 v2 路由，没有检查冲突技能。

**验收证据：**

- `.agents/skills/codex-autoresearch/SKILL.md` 不存在；
- 若保留，`.agents/audit/codex-autoresearch-legacy/SKILL.md` 存在；
- skill discovery 清单只包含 v2 与 v2-dev 两个 autoresearch 名称；
- 全仓活动文档和测试不再指导调用 `$codex-autoresearch`。

### AR2-P0-002：PowerShell 状态失败但进程退出 0

**严重级别：P0**
**状态：已复现**

`scripts/remote/autoresearch-v2.ps1:282` 对 `baseline/run/resume/status/collect/stop/sync-best` 调用 bridge 时使用 `-AllowFailure`。随后 `scripts/remote/autoresearch-v2.ps1:296` 根据 bridge 退出码写入本地 JSON 的 `ok`，但脚本末尾没有传播 `$result.exit_code`。只有进入 `catch` 时才在 `scripts/remote/autoresearch-v2.ps1:307` 执行 `exit 1`。

使用现有 fake SSH fixture 模拟 bridge 输出 `{"ok":false}` 并退出 7，实测：

```json
{
  "mode": "status",
  "powershell_exit_code": 0,
  "local_status_ok": false
}
```

对照测试中，`doctor` 没有使用 `-AllowFailure`，同样的远端退出 7 会进入 catch，实测 PowerShell 退出 1。因此缺陷的确定范围是上述七个统一 bridge mode；不要错误声称 doctor 当前也吞掉了退出码。

**所需修复：**

1. 将“解析输出、写本地 status、决定最终退出码”集中为单一 helper，所有 bridge mode 共用。
2. bridge 非零时必须先写本地 status JSON，且 `ok=false`，然后 PowerShell 退出非零。
3. 不要求保留远端的具体退出码时，至少统一退出 1；若选择原样传播，必须定义 SSH/PowerShell 可表示范围并测试。
4. 非 JSON 错误输出也必须保留在 `details.raw` 或 `details.error`，不能因 `ConvertFrom-Json` 再次抛错而丢失原始诊断。
5. 保持 `doctor/bootstrap/inspect/apply/deploy` 当前的非零行为，并用同一 helper 消除模式间差异。

**必要测试：**

- 参数化覆盖 `baseline/run/resume/status/collect/stop/sync-best`：fake bridge 非零，status 文件存在、`ok=false`、PowerShell 非零；
- fake bridge 非零且输出不是 JSON：仍写本地失败状态并退出非零；
- doctor 非零传播的现有正确行为增加回归测试。

### AR2-P0-003：TimeoutExpired 丢弃已生成的合法指标

**严重级别：P0**
**状态：已复现**

`scripts/remote/remote-bin/autoresearch_v2_driver.py:596-605` 直接调用 `subprocess.run(..., timeout=...)`。`TimeoutExpired` 没有单独捕获，而是在 `run_worker_once()` 的 `except Exception`（第 696 行）中统一标记失败。metric parser 只在第 612 行调用，因此 timeout 后永远不会执行。

最小复现预先在 trial 结果目录放置合法指标 `primary_metric=0.77`，然后让训练进程抛出 `TimeoutExpired`。实测：

```json
{
  "exception": "TimeoutExpired",
  "metric_file_exists": true,
  "results_exists": false,
  "worker_status": "failed",
  "pid": null,
  "last_event": "worker-failed",
  "event_has_completion_reason": false
}
```

这证明预算结束和试验失败目前被错误地合并成一个语义。

**所需修复：**

1. 单独捕获 `subprocess.TimeoutExpired`。
2. timeout 后仍调用现有 `measure_metric()`：
   - 指标合法：进入与正常完成完全相同的 threshold/keep/discard 决策路径；
   - 指标缺失或非法：记录 `decision=crash`。
3. 不要为 `TimeoutExpired` 伪造 124。Python timeout 异常没有可靠的子进程 return code；建议字段定义为：
   - `completion_reason="timeout"`
   - `process_exit_code=null`
   - `timed_out=true`
   - `metric_extracted=true|false`
4. 正常完成使用 `completion_reason="completed"`；非零退出使用 `process_error`；parser 失败使用 `metric_error`。
5. 把 metric 解析、threshold 比较、keep/discard、best 更新、结果写入抽成一个 finalize 函数，正常完成与 timeout 不得拥有两套判定代码。

### AR2-P0-004：失败 trial 没有进入 results.tsv，三类审计记录无法关联

**严重级别：P0**
**状态：已复现**

成功路径在 `autoresearch_v2_driver.py:654-684` 写 state、`results.tsv` 和 `events.jsonl`。异常路径在第 696-722 行只更新 state 并追加 `worker-failed` event，不调用 `append_results_row()`。

最小复现让 worker 命令退出 7。baseline 之后启动一个失败 trial，实测：

- `results.tsv` 仍只有 baseline 一条数据行；
- worker 状态为 `failed`，PID 已清空；
- worker worktree HEAD 仍停在失败 trial 的 commit，而不是 retained best；
- `worker-failed` event 只有 `worker/phase/trial_id/error/traceback`，缺少 `commit/run_dir/completion_reason`。

当前 `RESULTS_HEADER`（`autoresearch_v2_common.py:21-34`）本身也没有 `trial_id`、`completion_reason`、`process_exit_code`、`metric_extracted` 或 `error_type`，无法满足三类记录严格一致的要求。

**所需修复：**

1. 每个已经分配 `trial_id` 并开始执行的 trial 必须恰好产生一条 authoritative result row。
2. 失败行：`decision=crash`、metric/delta 留空、`error_type` 为简短稳定类型。
3. 构造一个 canonical trial outcome 对象，至少包含：
   - worker
   - phase
   - trial_id
   - branch
   - commit
   - run_dir
   - completion_reason
   - process_exit_code
   - metric_extracted
   - metric
   - decision
   - error_type
4. state、TSV 和 event 必须从同一个 outcome 对象生成，禁止各自拼接字段。
5. `trial_id` 必须作为幂等键，避免恢复或重试重复追加结果行。
6. 扩展 TSV header 时必须处理已有旧 header：显式拒绝旧 schema、提供迁移，或写入版本化新文件；不能直接向旧列数文件追加新格式行。
7. 推荐先原子写入每个 trial 的 outcome JSON，再在锁内幂等更新 TSV/event/state；否则三个独立文件无法真正获得事务一致性。
8. crash 后尝试把 worker worktree reset 到当前 `best_commit`。reset 本身失败时保留原始异常，并在 outcome 中追加 cleanup error。

**关于资源清理的校正：**

- `update_worker_status(... status="failed")` 已在 `autoresearch_v2_driver.py:232-233` 清空 PID；
- GPU lease 已在 `autoresearch_v2_driver.py:723-725` 的 `finally` 中释放；
- worker 不会残留为 `running`。

修复时应保留这些行为并增加测试，不应把它们描述成尚未实现。可以额外在 lease 释放后清空 worker 的 `gpu` 字段，避免状态看起来仍占用 GPU。

### AR2-P1-005：重复 baseline 破坏 retained best

**严重级别：P1**
**状态：已复现**

`autoresearch_v2_driver.py:621-622` 在 `phase == "baseline"` 时无条件 `keep=True`。`baseline` 字段只在为空时写入（第 633-634 行），但 best metric、best commit 和 best branch 每次 keep 都会更新（第 629-632 行）。

实际执行两次 baseline，第一次指标 0.50，第二次指标 0.10（方向 higher），结果为：

```json
{
  "second_decision": "keep",
  "best_before": 0.5,
  "best_after": 0.1,
  "baseline_after_metric": 0.5
}
```

即 retained best 已退化为 0.10，但 baseline 仍声称 0.50，状态内部互相矛盾。

**所需修复：**

1. 在 baseline trial 启动前、持有 state lock 时检查 `state["baseline"] is None`；存在时立即明确失败，避免浪费训练预算。
2. finalize 时再次在 lock 内检查，阻止两个并发 baseline 同时通过预检。
3. baseline 首次成功建立时才允许初始化 `baseline/best_metric/best_commit/best_branch`。
4. 普通 run 继续沿用当前 threshold 判定；这部分当前实现正确。
5. discard 继续 reset 到 `best_commit_before`；这部分当前实现正确。
6. crash 增加 reset 到当前 retained `best_commit`；当前实现缺失。

**必要测试：**

- 第二次 baseline 返回非零，state、best branch 和 results 均不变；
- 两个并发 baseline 最多一个成功；
- 普通 run 未超过 threshold 时不得更新 best；
- discard 和 crash 后 worker HEAD 都等于 retained best commit。

### AR2-P1-006：doctor 无条件成功

**严重级别：P1**
**状态：已复现**

`autoresearch_v2_driver.py:807-818` 始终返回 `ok=True`。`git_available` 只是信息字段，不参与退出码。

用绝对 Python 路径启动 driver，同时把 `PATH` 清空，实测：

```json
{
  "exit_code": 0,
  "ok": true,
  "git_available": false
}
```

**所需修复：**

1. doctor 返回结构化 `checks[]`，每项至少包含 `name/ok/required/detail`。
2. 必需检查至少包括：
   - `sys.executable` 存在且可执行；
   - Git 可发现并能运行；
   - run root、worktree root、lease root 可创建、可写并可清理探针文件；
   - bridge 所需 Python 模块文件存在；
   - 若已有 run state，state 中的目标 repo 存在且是 Git repo。
3. “目标已提供时检查 repo”在当前 CLI 中定义不完整：doctor 没有 `--target` 参数。修复时应选择并固定一种接口：
   - 增加可选 `--target`，解析 target YAML 后检查；或
   - 当指定 run tag 已有 state 时检查 `state.repo_root`；无 state 时明确标记 `target_repo=not_checked`。
4. 任一 required check 失败：payload `ok=false`，driver 退出非零。
5. PowerShell doctor 当前已能传播远端非零退出，应添加 regression test。若重构为 `-AllowFailure`，必须显式传播退出码，不能引入 AR2-P0-002 同类错误。

## 4. 发布副本同步要求

以下根目录文件在 `plugins/codex-autoresearch-v2/` 内有同源副本，当前 hash 相同：

- `scripts/remote/autoresearch-v2.ps1`
- `scripts/remote/remote-bin/autoresearch_v2_driver.py`
- `.agents/skills/codex-autoresearch-v2/SKILL.md`

正式修复时必须同步更新 plugin 内对应文件。现有 `test_versioned_plugin_package_contains_invoke_skill_and_runtime` 只检查文件存在，不检查内容相等。

应新增 parity 测试，对所有打包 runtime、PowerShell library、skill 和 reference 逐一比较内容 hash。若项目有正式打包脚本，应通过脚本重新生成 plugin，避免人工复制漂移。功能变化还应按项目版本策略更新 `.codex-plugin/plugin.json` 的版本号，并与 `.codex/research-policy.json` 保持一致。

## 5. 建议修改文件清单

以下是修复阶段的预计范围，不代表本次审计已经修改：

1. 移动/删除：
   - `.agents/skills/codex-autoresearch/**`
   - 可选归档到 `.agents/audit/codex-autoresearch-legacy/**`
2. runtime：
   - `scripts/remote/autoresearch-v2.ps1`
   - `scripts/remote/remote-bin/autoresearch_v2_driver.py`
   - `scripts/remote/remote-bin/autoresearch_v2_common.py`
3. plugin 同步副本：
   - `plugins/codex-autoresearch-v2/scripts/remote/autoresearch-v2.ps1`
   - `plugins/codex-autoresearch-v2/scripts/remote/remote-bin/autoresearch_v2_driver.py`
   - `plugins/codex-autoresearch-v2/scripts/remote/remote-bin/autoresearch_v2_common.py`
   - 若合约文字变化，同步 plugin 内 skill/references/assets
4. tests：
   - `tests/test_remote_autoresearch_v2.py`
   - `tests/test_remote_autoresearch_v2_wrapper.py`
   - `tests/test_autoresearch_v2_modes.py`
   - 建议新增 `tests/test_autoresearch_v2_package_parity.py`
5. 文档/策略：
   - 只有在路径、schema 或版本变化时更新 `.codex/research-policy.json`、README 和 plugin manifest；不要改训练参数、数据路径或模型代码。

## 6. 修复测试矩阵

| 测试 ID | 必须验证的行为 | 建议位置 |
|---|---|---|
| T1 | 七个 `-AllowFailure` mode 的 bridge 非零均写 `ok=false` 且 PowerShell 非零 | wrapper test，参数化 |
| T2 | bridge 非零且输出非 JSON 仍保留 raw error | wrapper test |
| T3 | timeout + 合法指标进入正常 keep | driver test |
| T4 | timeout + 合法但未改善指标进入 discard，并回滚 worktree | driver test |
| T5 | timeout + 无指标写一条 crash result | driver test |
| T6 | 普通非零进程/metric parser 异常也各写一条 crash result | driver test |
| T7 | state、TSV、event 的 worker/trial_id/commit/run_dir/completion_reason 完全一致 | driver test |
| T8 | crash 后 PID 为空、lease 文件释放、worker 非 running、HEAD 回到 best | driver test |
| T9 | 重复 baseline 被拒绝，best/state/branch/results 不变 | driver test |
| T10 | 并发 baseline 只有一个成功 | driver test |
| T11 | doctor 在 Git 缺失、目录不可写、目标 repo 非 Git 时失败 | driver test |
| T12 | PowerShell doctor 传播 driver doctor 非零 | wrapper test |
| T13 | `.agents/skills/codex-autoresearch/` 不存在，v2/v2-dev 存在 | project/mode test |
| T14 | 根 runtime 与 plugin runtime 内容完全一致 | package parity test |
| T15 | 旧 TSV schema 的迁移或明确拒绝行为 | driver/common test |

所有测试必须使用临时目录、fake SSH/进程、模拟 metric 和模拟 lease，不依赖真实 SSH、GPU 或 TVI-LFM 训练。

## 7. 完成验收命令

修复完成后至少执行：

```powershell
python -m unittest discover -s tests -p 'test_autoresearch_v2*.py' -v
python -m unittest discover -s tests -p 'test_remote_autoresearch_v2*.py' -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\run-local-checks.ps1 -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\guard-autoresearch-mode.ps1 -Mode develop -FromGit -Json
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .agents\skills\codex-autoresearch-v2
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .agents\skills\codex-autoresearch-v2-dev
```

交付说明必须列出：

1. 实际修改文件；
2. 每个缺陷对应的自动化测试；
3. 完整测试命令和结果；
4. plugin parity 结果；
5. 明确声明真实 SSH/GPU 是否验证。

## 8. 远程验证边界

本报告没有执行真实 SSH、GPU lease 或 TVI-LFM trial，因此只能证明本地代码路径和模拟契约存在上述问题。正式修复可先以本地 fake transport 测试作为合并门槛，但在完成一次真实 bounded trial 前，不得声称远程 GPU 闭环已经通过。
