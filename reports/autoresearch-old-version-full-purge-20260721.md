# Autoresearch 旧版本全量清理记录

审计与清理时间：2026-07-20 23:49 至 2026-07-21 00:05（Asia/Shanghai）

## 范围与判定

本次覆盖本地工作区、用户级 Codex/Agents 目录、服务器 `/home/cgv841/ybj`、服务器用户调度、进程、Git worktree、分支/tag、runtime staging、state roots、uploads、runs、leases、归档和 Python 缓存。

删除条件为：对象属于旧协议或旧部署；没有活动进程、调度或生产入口引用；不属于当前 schema-v2 runtime；删除目标可精确限定。研究 checkpoint、训练结果和当前运行中的 A3/E4 流水线不因包含旧 provenance 字符串而删除。

## 本地清理

- 删除 `.agents/audit/codex-autoresearch-legacy/`：107 个 tracked 文件，已退出 skill 发现路径且不再承担当前测试职责。
- 删除旧 `autoresearch/program.md`、缺少 schema 版本的 `autoresearch/targets/tvilfm-stage-a.yaml` 和旧错误报告 `reports/autoresearch-v2-formal-error-report.md`。
- 删除 25 组 `autoresearch-runs/` 旧状态快照：317 个文件、1,466,134 字节；这些 target 均不是严格整数 `schema_version: 2`。
- 删除 2 个旧项目 program 与 4 个无 schema 的 target，共 8,815 字节。
- 删除 22 个 dry-run、bounded-unit、smoke、旧 ablation/audit 实验目录：39 个文件、63,565 字节。
- 删除本地 tag `archive/local/20260713/codex-upload-autoresearch-v2`，原 OID 为 `e6a072c58e7655a98d044f3b27bb01cfe8f2dcd8`。
- 服务器分支清理后，对 `REID-feature-domain-gap` 执行 `fetch --prune`，移除 16 条失效的 `origin/autoresearch/*` remote-tracking refs；未触碰其工作树和 4 个用户未跟踪文件。
- 用户级 `C:\Users\pbrii\.codex\skills`、plugin cache 与 `C:\Users\pbrii\.agents` 未发现旧 autoresearch 安装副本。

本地共删除 472 个文件、5,070,034 字节。tracked 删除仍可由 Git 历史恢复；原本未跟踪的 run/dry-run 状态没有恢复保证。

## 服务器清理

- 清空旧 state 内容但保留当前可复用的空根：24 个旧 run（318 文件、1,391,763 字节）、21 个 upload（42 文件、57,512 字节）和空 worktree。
- 删除 4 组 staging CPU fixture/canary：208 文件、109,786 字节；保留 `0.2.0/bin/` 与 `SHA256SUMS`。
- 删除服务器 `bin/__pycache__` 与 staging `bin/__pycache__`：6 个 `.pyc`、68,961 字节，其中包含已退役的 TVI-LFM parser 字节码。
- 删除两个旧版本归档：`autoresearch-v2-runtime-pre-0.2.0-20260720` 与 `autoresearch-legacy-bin-20260720`，共 10 文件、79,301 字节。其旧文件 SHA 已记录在此前审计报告，但归档副本本身不再保留。
- 删除未跟踪的 `Single-experiment/docs/autoresearch_baseline_consolidation_plan.md`；该文档已自述 archived/retired，且没有活动引用。
- 删除 16 条 `refs/heads/autoresearch/*`；删除前逐条验证均已并入 `main`。
- 删除 18 个 `refs/tags/archive/20260709/autoresearch-*` 旧 run/smoke tag。未运行 `git gc`，但不再承诺这些 tag 指向提交可恢复。
- `runs/`、`uploads/`、`worktrees/` 现在为空；`leases/.lock` 保留为当前协调机制。

删除前确认旧 run/upload 中不存在 `.pth`、`.pt`、`.ckpt`、`.bin` 或 `.safetensors`，也不存在整数 `schema_version: 2` target。crontab 和 user systemd 中无 autoresearch 调度。

## 删除的服务器分支 tip

| OID | 对应旧分支组 |
|---|---|
| `68fd381aee9e60960f38b93de084a8b3887a3446` | external-screen 初始 best/w1 与 20260714b best |
| `e0fd3e0a4291d3f804a09746b276cdff0f1dad22` | external-screen 20260714b w1 与 verify best/w1 |
| `5f98711ff5aa73cb7e6e653424001791dff7ed01` | external-screen-full best/w1 |
| `64e17f683578b27b4b765f518ca4b1747a1725de` | fdgap E4/H1 20260713a best/w1 |
| `4e3344a420a000259a54d97136b285ee6bc96322` | fdgap E4/H1 20260713b best/w1 |

## 保留项及理由

- 当前 canonical skill、dev skill、versioned plugin、generic runtime、tests、policy、schema-v2 program/target 示例：活动实现。
- `config/autoresearch.example.psd1`：当前 mode/sealed-path 项目配置，并非旧 schema target。
- `config/autoresearch-train.*` 与 manual submit/check/cancel 链：仍被人工训练入口引用，职责独立于 generic runtime，不能判为冗余。
- 服务器 `/home/cgv841/ybj/autoresearch-v2/` 空 state 根与 `leases/.lock`：未来 schema-v2 run 的当前协调路径。
- 服务器 `/home/cgv841/ybj/autoresearch-v2-staging/0.2.0/bin/`、`SHA256SUMS` 和生产 bridge：当前生产部署。
- `/home/cgv841/ybj/archives/ybj_inactive_experiments_20260720T2233/`：研究实验归档，不是旧 runtime 归档。
- TVI-LFM/PMT-SR 结果、checkpoint、日志、manifest 中的历史 `autoresearch` 字符串：实验 provenance，不按 runtime 冗余删除。
- Git commit/object 历史、远端 GitHub 分支与当前审计报告：未做历史重写或远端删除。

## 最终安全状态

- 生产 runtime 四个 SHA-256 在清理前后保持：`common c6d57245…`、`driver 10afa469…`、`gpu_lease 060567a5…`、`bridge ee951831…`。
- 服务器 tracked 状态仍仅为原有三个 TVI-LFM 修改。
- A3/E4 父进程 PID `2087629` 与 GPU 主进程 PID `2087809` 保持；DataLoader worker 正常轮换。
- `nvidia-smi` 仍只报告 PID `2087809` 为 compute process；清理未启动 GPU 或训练任务。
