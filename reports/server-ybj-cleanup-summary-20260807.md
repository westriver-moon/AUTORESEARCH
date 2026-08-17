# ybj 服务器备份修复与最终清单（2026-08-07）

重复备份逻辑已修复并通过跨 cron 周期验证。本报告和清单只定义待确认删除范围；尚未删除服务器上的任何文件。

## 根因与修复

备份目录 `/home/cgv841/ybj/non_research/codex_proxy/backups/` 不是 autoresearch 实验输出。原调用链为：

```text
crontab（每分钟）
  -> ensure-vscode-proxy-active.sh
  -> install-all-vscode-code-server-hooks.sh
  -> install-vscode-code-server-hook.sh
  -> cp -p code-server 到 backups/code-server.<commit>.<timestamp>.bak
```

`install-vscode-code-server-hook.sh` 原先先执行备份，之后才检查 `CODEX_PROXY_HOOK` 是否已经存在。因此，每分钟的自愈任务即使不需要修改文件，也会对每个 VS Code Server commit 创建一份新备份。

修复后，脚本先检查 hook；已安装时立即成功退出，只有首次实际修改 launcher 时才创建备份。修改采用临时文件、语法检查、插入结果检查和原子替换，脚本 SHA-256 为：

```text
88525a7c0961b9d6db3b914056dad59830bfd5c46cc9b9e707d552623f6606db
```

## 验证结果

- 修复后手动运行完整安装链，备份数保持 `214,774 -> 214,774`。
- 连续观察 150 秒、5 次采样，数量始终为 `214,774`，已跨过至少两个分钟级 cron 周期。
- 最终清单生成后再次运行完整安装链，数量仍保持 `214,774 -> 214,774`。
- 最终删除列表共 214,766 行，去重后仍为 214,766 行；所有路径均处于批准候选范围，没有越界路径。

## 最终文件

- `server-ybj-cleanup-manifest-20260807.tsv`：完整分类清单，共 214,796 个数据行，70,879,921 字节。
- `server-ybj-final-delete-list-20260807.txt`：最终待确认删除路径，一行一个绝对路径，共 214,766 行。

哈希：

```text
manifest SHA-256: EE9E577D821F10F76BB0E0913F6A680A897DA0DC1B9A4C2070383A70B47AB989
delete list SHA-256: DE86764E3DF613204EADDD8F683159804A48347E11797574ECB610B5F5A9E846
```

| 动作 | 类别 | 文件数 | 逻辑大小 | 结论 |
| --- | --- | ---: | ---: | --- |
| `delete_after_confirmation` | `proxy_backup` | 214,762 | 247,710,837 B | 每个 code-server 标识保留文件名时间戳最新的一份，其余列入最终待删清单。 |
| `retain_latest_per_group` | `proxy_backup` | 9 | 9,900 B | 每组最新备份，排除在删除列表之外。 |
| `retain_manual_review` | `proxy_backup` | 3 | 5,175 B | `proxy-env` / `server-env-setup` 特殊备份，排除在删除列表之外。 |
| `delete_after_confirmation` | `python_cache` | 3 | 49,009 B | 可再生成的 `autoresearch-v2/__pycache__/*.pyc`。 |
| `delete_after_confirmation` | `empty_root_artifact` | 1 | 0 B | 根目录 `%ln` 空文件。 |
| `archive_review_required` | `recovery_archive` | 18 | 1,035,299,422 B | 恢复/溯源归档，全部排除在最终删除列表之外。 |

## 删除边界

后续如获确认，只能按 `server-ybj-final-delete-list-20260807.txt` 中的精确路径执行，并在执行前重新核对该文件的 SHA-256。`retain_*` 和 `archive_review_required` 项不应删除；`git-archives/` 需要单独的保留、冷存储或删除决定。
