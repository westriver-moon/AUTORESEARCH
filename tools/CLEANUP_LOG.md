# Cleanup log

Scope: `/home/cgv841/ybj` on the 3090 server only. No NVMe path was touched, and no file owned by another user was removed.

## Removed

- Incomplete RegDB checkpoint relay fragment: 132,349,952 bytes. It was verified smaller than the 606,215,986-byte source and therefore invalid. The complete source checkpoint remains unchanged on the 4090 server with its recorded SHA-256.
- `SALT_VI_PAPER_VISUALS_20260728.tar.gz`: 114,593,743 bytes. The extracted directory and the consolidated evidence copy both remain; the archive is reproducible from that directory.
- `SALT_VI_ALL_FIGURES_CATALOG_20260728.tar.gz`: 9,610,141 bytes. Its 19 member paths and all member SHA-256 values were verified identical to the retained ZIP before deletion.
- Superseded sanitizer run logs inside the export were removed before the final checksum pass; the final sanitizer log is stored outside the export so the package remains checksum-stable.
- The private exact RegDB source tar copied to the 3090 consolidation directory was replaced by an anonymized tar. The exact original remains on the 4090 source server.

Stable redundant archive cleanup: 124,203,884 bytes. Including the invalid checkpoint fragment, 256,553,836 bytes of unusable or reproducible copies were removed.

## Explicitly preserved

- All winning SYSU checkpoints in the 3090 export.
- All ten RegDB selected checkpoints on the 4090 source server.
- Original training/evaluation logs, structured events, configs, commands, visual data, caption resources, and source repositories.
- All files outside the user's `ybj` scope.
