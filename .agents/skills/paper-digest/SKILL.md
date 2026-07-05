---
name: paper-digest
description: Project-local workflow for parsing Zotero paper PDFs into structured JSON, Markdown reading cards, and a lightweight paper knowledge graph. Use when the user invokes $paper-digest or asks Codex to read, parse, digest, summarize, analyze, or build notes/knowledge graphs from papers already imported into the local Zotero candidate library.
---

# Paper Digest

## Core Rule

Use the project script:

```powershell
python research-ops\scripts\paper_digest.py ...
```

Do not reimplement Zotero reads, PDF text extraction, reading-card generation, or graph writes inside the Skill. The script is the source of truth for the current local workflow.

## Safety Defaults

- Read only from local Zotero Desktop through `http://127.0.0.1:23119/api`.
- Write generated artifacts only under `research-ops/library/parsed/`, `research-ops/notes/papers/`, and `research-ops/library/kg/`.
- Do not modify Zotero items, collections, annotations, or PDFs.
- Do not connect SSH, start GPU jobs, call `$codex-autoresearch`, or run training.
- Do not call cloud LLMs unless the user explicitly asks for LLM-based summarization later.

## Default Target

Default to the candidate paper collection configured in `research-ops/config/library.json`:

```powershell
--collection-key V6A358QD
```

This corresponds to the Zotero candidate collection / target `C25`.

## Command Patterns

Parse one paper by title or partial title in the candidate collection:

```powershell
python research-ops\scripts\paper_digest.py --title "MambaPro"
```

Parse one paper by title across the whole local Zotero library:

```powershell
python research-ops\scripts\paper_digest.py --title "Learning Progressive Modality-Shared Transformers" --all-zotero
```

Parse the five most recently modified candidate papers:

```powershell
python research-ops\scripts\paper_digest.py --limit 5
```

Parse one specific Zotero item:

```powershell
python research-ops\scripts\paper_digest.py --item-key DH67KGHN
```

Overwrite existing notes after improving extraction logic:

```powershell
python research-ops\scripts\paper_digest.py --limit 5 --force
```

Extract more PDF pages per paper:

```powershell
python research-ops\scripts\paper_digest.py --limit 3 --max-pages 16
```

## Outputs

- Parsed JSON and extracted text:

```text
research-ops/library/parsed/
```

- Markdown reading cards and index:

```text
research-ops/notes/papers/
```

- Lightweight knowledge graph:

```text
research-ops/library/kg/paper_graph.json
research-ops/library/kg/nodes.jsonl
research-ops/library/kg/edges.jsonl
```

## Workflow

1. Check Zotero Desktop is open:

```powershell
python research-ops\scripts\zotero_status.py
```

2. Run `paper_digest.py` with the requested item keys or collection limit.
3. Prefer `--title` for user-facing requests. Use `--item-key` only when the user provides a Zotero key or title matching is ambiguous.
4. If title matching reports multiple close matches, show the candidate list and ask the user to pick one item key. Do not guess.
5. Summarize the JSON output: item count, notes written, PDF extraction status, detected datasets/methods/metrics, and graph node/edge counts.
6. If the user asks for richer parsing backends, read `references/github-backends.md` and propose a staged upgrade.
