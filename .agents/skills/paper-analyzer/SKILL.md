---
name: paper-analyzer
description: Project-local deep paper analysis workflow adapted from zsyggg/paper-craft-skills paper-analyzer. Use when the user explicitly invokes $paper-analyzer or asks Codex to produce high-quality long-form paper notes, academic HTML articles, formula/method explanations, source-code-aligned analysis, or a deeper replacement for paper-digest from Zotero papers.
---

# Paper Analyzer

## Core Rule

Use this project workflow instead of the upstream `/paper-analyzer` command:

```powershell
python research-ops\scripts\paper_analyzer_prepare.py ...
```

Then write the final article to the generated `article.md` and render HTML with:

```powershell
python .agents\skills\paper-analyzer\scripts\generate_html.py <article.md> <article.html>
```

## Safety Defaults

- Read Zotero Desktop through the local API only.
- Do not modify Zotero items, collections, notes, annotations, or PDFs.
- Write outputs only under `research-ops/analysis/papers/`.
- Clone or inspect code only under `research-ops/tmp/paper-code/` when code analysis is needed.
- Do not connect SSH, use GPU, start training, or call `$codex-autoresearch-v2`.
- No extra API key is required by this Skill.

## Source And Adaptation

This Skill is adapted from `zsyggg/paper-craft-skills`, path `skills/paper-analyzer`.

- Upstream instructions are preserved in `references/upstream-SKILL.md`.
- Source metadata is in `references/source.md`.
- Upstream style references are in `styles/`.
- Upstream helper scripts are in `scripts/`.

## Command Patterns

Prepare a Zotero paper by title from the candidate collection:

```powershell
python research-ops\scripts\paper_analyzer_prepare.py --title "MambaPro" --force
```

Prepare a paper from the whole local Zotero library:

```powershell
python research-ops\scripts\paper_analyzer_prepare.py --title "Learning Progressive Modality-Shared Transformers" --all-zotero --force
```

Prepare a specific Zotero item:

```powershell
python research-ops\scripts\paper_analyzer_prepare.py --item-key 4XFWQY7H --force
```

Render the final article:

```powershell
python .agents\skills\paper-analyzer\scripts\generate_html.py research-ops\analysis\papers\<paper>\article.md research-ops\analysis\papers\<paper>\article.html
```

## Workflow

1. Run `python research-ops\scripts\zotero_status.py --json` and confirm Zotero local API is available.
2. Run `paper_analyzer_prepare.py` using `--title`, `--all-zotero`, or `--item-key`.
3. Read the generated `analysis_input.md` completely enough to understand the paper. If needed, read the full extracted text sections from that file.
4. If GitHub URLs are detected, inspect the repository in `research-ops/tmp/paper-code/` and connect paper components to implementation files. If no code is available, state that clearly.
5. Use the upstream style references only as needed:
   - `styles/academic.md` for academic long-form notes.
   - `styles/concise.md` for dense quick-read notes.
   - `styles/storytelling.md` for public-facing explanatory writing.
   - `styles/with-code.md` when source code is available.
   - `styles/with-formulas.md` when formulas need detailed explanation.
6. Write a high-quality Chinese article to the generated `article.md`. Default style is `academic` unless the user asks otherwise.
7. Render `article.html` with the upstream `generate_html.py` script.
8. Summarize the output paths, code status, PDF extraction status, and any remaining limitations.

## Quality Bar

- Do not output a shallow template.
- Explain the paper's research problem, core insight, method pipeline, key modules, experimental evidence, limitations, and relevance to the user's current ReID/SYSU/PMT work.
- Include concrete numbers from the paper when available.
- If code is available, map at least two paper concepts to source files or clearly state why code mapping was not performed.
- Prefer fewer but more accurate claims over broad generic praise.
