---
name: paper-to-zotero
description: Project-local workflow for searching papers with arXiv/OpenAlex and importing them into the user's local Zotero Desktop library. Use when the user explicitly invokes $paper-to-zotero or asks Codex to find/crawl/search papers and add/import/open them in Zotero, especially for the candidate paper target C25, unread target C22, read target C21, arXiv PDFs, OpenAlex fuzzy discovery, CCF AI A/B discovery, or local Zotero reading workflows.
---

# Paper To Zotero

## Core Rule

Use the project script:

```powershell
python research-ops\scripts\zotero_local_ingest.py ...
```

Do not reimplement paper retrieval or Zotero writes in the Skill. The script is the source of truth for retrieval, PDF caching, local Zotero Connector writes, duplicate checks, and `research-ops` SQLite updates.

## Safety Defaults

- Use dry-run unless the user explicitly says to import, write, add to Zotero, or open/read in Zotero.
- Add `--yes` only when the user clearly authorizes writing to Zotero.
- Add `--open` only when the user asks to open/read after import.
- Do not use Zotero Web API credentials. This project writes only through local Zotero Desktop.
- Do not call SSH, GPU training, or `$codex-autoresearch-v2`.
- Do not use `--force-duplicate` unless the user explicitly asks for duplicates.

## Target Collections

Default to the Zotero candidate paper collection:

```powershell
--target C25
```

Use these known local targets when requested:

- Candidate paper collection: `--target C25`
- Unread collection: `--target C22`
- Read/completed collection: `--target C21`
- ReID multimodal paper parent collection: `--target C17`
- CLIP and improvements collection: `--target C20`
- Searchable encrypted database project collection: `--target C24`
- My Library: `--target L1`

If the user names a collection not listed here, first run a dry-run or call Zotero selected-collection metadata before writing.

## Source Selection

- Use `--source arxiv` for CS/ML preprints, when PDF availability matters, or when the user asks for arXiv.
- Use `--source openalex` for broad or fuzzy discovery across venues. OpenAlex may not expose a direct PDF URL.
- Use `--source all` when the user asks for broad discovery plus arXiv coverage.
- Add `--title-only` for OpenAlex only when the user asks for an exact title-like query. Omit it for fuzzy discovery.
- Use `--profile ccf-ai-ab` for AI-domain CCF-A/B conference discovery, including CVPR, ICCV, ECCV, AAAI, NeurIPS, ACL, ICML, IJCAI, EMNLP, NAACL, COLING, UAI, and other CCF AI A/B venues.
- Use `--ccf-rank A`, `--ccf-rank B`, or `--ccf-rank AB` when the user asks for a specific CCF tier.
- Use `--venue-group vision` for "top three vision conferences" or CVPR/ICCV/ECCV requests.
- Other venue groups: `all`, `ml`, `nlp`, `general-ai`, `robotics`.

arXiv can return `429 Rate exceeded`; if this happens, report it as external rate limiting and suggest retrying later or using OpenAlex.

## Command Patterns

Preview only:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "graph neural network" --limit 3 --target C25 --download-pdf --no-db
```

Import into the candidate paper collection:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "graph neural network" --limit 3 --target C25 --yes
```

Import and open for reading:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "graph neural network" --limit 3 --target C25 --yes --open
```

Fuzzy OpenAlex discovery:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source openalex --query "visible infrared person re-identification" --limit 5 --target C25 --yes
```

CCF AI A/B venue-aware preview:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source openalex --profile ccf-ai-ab --ccf-rank AB --query "visible infrared person re-identification" --limit 5 --target C25 --no-db
```

Vision top-three CCF preview:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source openalex --profile ccf-ai-ab --venue-group vision --ccf-rank AB --query "visible infrared person re-identification" --limit 5 --target C25 --no-db
```

## Workflow

1. Parse the user's request into query, source, limit, target, write/open intent, and whether fuzzy discovery is desired.
2. Before running the ingest script, ensure Zotero Desktop is open by running:

```powershell
python research-ops\scripts\zotero_status.py
```

3. Run the generated `zotero_local_ingest.py` command.
4. Summarize the JSON output: searched source, titles, PDF status, Zotero item keys, attachment keys, target collection, and any rate-limit/error messages.
5. If the command was dry-run and results look good, offer the exact `--yes` command to import.
