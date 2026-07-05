# Phase 2 Research Ops Report

## Summary

Status: PASS for project-local research library setup.

`research-ops/` has been created with a long-term paper database structure,
retrieval scripts, Zotero integration scaffolding, and safe ignore rules for
generated data and secrets.

Zotero Desktop data directories exist on this machine, but Zotero Desktop's
local API is not currently listening and Zotero Web API credentials are not yet
configured. Therefore Zotero write sync remains disabled. A Zotero item preview
export was generated instead.

## Created Structure

```text
research-ops/
  README.md
  config/
    library.json
    zotero.example.json
  schemas/
    sqlite-schema.sql
  scripts/
    init_paper_library.py
    lookup_papers.py
    zotero_status.py
    export_zotero_preview.py
  library/
    db/
    raw/
      openalex/
      arxiv/
    records/
    pdf/
    exports/
    zotero/
    logs/
```

Project ignore rules were added in `.gitignore` for secrets and generated
artifacts:

```text
.env
*.local.json
research-ops/config/zotero.local.json
research-ops/library/db/*.sqlite
research-ops/library/raw/**
research-ops/library/pdf/**
research-ops/library/zotero/**
```

Placeholder `.gitkeep` files preserve the directory structure.

## Database

SQLite database:

```text
research-ops/library/db/papers.sqlite
```

Schema:

```text
research-ops/schemas/sqlite-schema.sql
```

Tables:

| Table | Purpose |
|---|---|
| `papers` | Normalized paper metadata and canonical IDs. |
| `authors` | Ordered author list per paper. |
| `identifiers` | DOI, arXiv ID, OpenAlex ID, and other identifiers. |
| `retrievals` | API retrieval audit trail without storing API keys. |
| `zotero_links` | Future mapping from local records to Zotero items. |

Validation result:

| Metric | Count |
|---|---:|
| Papers | 5 |
| Authors | 22 |
| Retrievals | 2 |
| OpenAlex papers | 3 |
| arXiv papers | 2 |

OpenAlex API key storage check:

```text
actual key in SQLite: false
endpoint api_key parameter in SQLite: false
```

## Retrieval Validation

Commands run:

```powershell
python research-ops\scripts\init_paper_library.py
python research-ops\scripts\lookup_papers.py --source openalex --query "graph neural network" --title-only --limit 3 --since 2025-01-01 --until 2026-07-04 --write-db
python research-ops\scripts\lookup_papers.py --source arxiv --query "graph neural network" --limit 2 --write-db
```

OpenAlex result: success.

arXiv result: success.

Inserted sample titles:

```text
SA-HGNN: Sample-Adaptive Hyperbolic Graph Neural Network for EEG-Based Depression Recognition
Method for Automated Decomposition of Monolithic Software Systems Based on Graph Neural Networks
Advanced battery state estimation in electric vehicles using graph neural network and evolutionary optimization
A graph neural network emulator predicting planet formation through the giant impact stage
Robust and Explainable 3D Mode Shape Recognition Using Region-Aware Graph Neural Networks
```

Raw responses were stored under:

```text
research-ops/library/raw/openalex/
research-ops/library/raw/arxiv/
```

These paths are ignored by `.gitignore`.

## Zotero Configuration

Configured now:

| Item | Status |
|---|---|
| Zotero Desktop profile directories | Present under `%APPDATA%\Zotero` and `%LOCALAPPDATA%\Zotero` |
| Zotero local API | Not running / connection refused |
| `ZOTERO_API_KEY` | Not configured |
| `ZOTERO_USER_ID` | Not configured |
| `ZOTERO_GROUP_ID` | Not configured |
| Zotero write sync | Disabled |
| Zotero preview export | Created |

Zotero preview file:

```text
research-ops/library/zotero/zotero-items-preview.json
```

This preview converts local SQLite records into Zotero-shaped item JSON but does
not write to Zotero.

To enable Zotero Web API sync later:

```powershell
setx ZOTERO_API_KEY "your_zotero_api_key"
setx ZOTERO_USER_ID "your_zotero_user_id"
setx ZOTERO_LIBRARY_TYPE "user"
```

For a group library:

```powershell
setx ZOTERO_GROUP_ID "your_zotero_group_id"
setx ZOTERO_LIBRARY_TYPE "group"
```

After setting credentials, restart Codex App or the shell session.

## Safety Boundaries

Confirmed:

- No SSH connection was made.
- No GPU or training process was started.
- `codex-autoresearch` was not invoked.
- No PDF download was performed.
- No real Zotero item was created, updated, or deleted.
- API keys were not written to project files or SQLite.

## Remaining Work

Before real Zotero sync:

1. Create or retrieve a Zotero API key.
2. Configure `ZOTERO_USER_ID` or `ZOTERO_GROUP_ID`.
3. Decide whether the target is a personal library or a group library.
4. Add a guarded `--push` workflow only after confirming collection semantics.

Recommended next step:

```powershell
python research-ops\scripts\zotero_status.py
```

Then configure Zotero credentials if Web API sync is required.

## Verdict

PHASE 2 PASSED WITH ZOTERO WRITE SYNC PENDING CREDENTIALS
