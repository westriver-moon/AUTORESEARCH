# Source Metadata

- Source repository: https://github.com/zsyggg/paper-craft-skills
- Source path: `skills/paper-analyzer`
- Installed path: `.agents/skills/paper-analyzer/`
- Commit SHA: `3be47a2a53cc35a411c587bca5231a08de57287a`
- Commit date: `2026-05-29T05:26:56Z`
- GitHub license metadata: not detected by GitHub API
- README claim: `MIT`

## Local Adaptation

- The upstream slash command is adapted to explicit Codex invocation as `$paper-analyzer`.
- The main `SKILL.md` is rewritten in ASCII for Windows validation stability.
- The original upstream `SKILL.md` is preserved as `references/upstream-SKILL.md`.
- Zotero integration is provided by `research-ops/scripts/paper_analyzer_prepare.py`.
- Outputs are constrained to `research-ops/analysis/papers/`.
