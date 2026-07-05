# Research Ops

Project-local paper retrieval and literature-library operations.

This directory is the long-term home for paper metadata, raw API responses,
normalization scripts, and Zotero integration scaffolding.

## What Is Enabled

- Project-local paper library structure under `research-ops/library/`.
- SQLite metadata database at `research-ops/library/db/papers.sqlite`.
- Raw response cache for OpenAlex and arXiv.
- Normalized paper records with DOI, arXiv ID, OpenAlex ID, authors, dates,
  URLs, PDF URLs, and source metadata.
- Zotero preview export from the SQLite library.
- Zotero status checks for local Zotero Desktop and Web API credentials.
- Local Zotero Desktop import through Zotero Connector HTTP Server.

## What Is Not Automatic

- No SSH connections.
- No GPU usage or training.
- No `codex-autoresearch` calls.
- No PDF downloading by default.
- No writes to Zotero unless `zotero_local_ingest.py --yes` is passed.
- No API keys stored in project files.

## Directory Layout

```text
research-ops/
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
    zotero_local_ingest.py
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

Generated data under `research-ops/library/` is ignored by `.gitignore` except
for placeholder files.

## Initialize

```powershell
python research-ops\scripts\init_paper_library.py
```

## Lookup Papers

OpenAlex title search and write to SQLite:

```powershell
python research-ops\scripts\lookup_papers.py --source openalex --query "graph neural network" --title-only --limit 5 --since 2025-01-01 --until 2026-07-04 --write-db
```

arXiv title search and write to SQLite:

```powershell
python research-ops\scripts\lookup_papers.py --source arxiv --query "graph neural network" --limit 3 --write-db
```

arXiv is rate-limited. Leave at least 3 seconds between arXiv calls.

## Zotero

Zotero integration is configured as a safe scaffold. It can inspect local
availability, export preview payloads, and import papers into the local Zotero
Desktop library through Zotero's Connector HTTP Server. It does not write to
Zotero by default.

Check status:

```powershell
python research-ops\scripts\zotero_status.py
```

Export Zotero item preview:

```powershell
python research-ops\scripts\export_zotero_preview.py
```

Dry-run a search and show the Zotero target that would receive the item:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "graph neural network" --limit 1 --target C25 --no-db
```

Dry-run with PDF download into the project cache, but still do not write Zotero:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "attention is all you need" --limit 1 --target C25 --download-pdf --no-db
```

Preview AI-domain CCF-A/B conference matches using the local venue-aware profile:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source openalex --profile ccf-ai-ab --ccf-rank AB --query "visible infrared person re-identification" --limit 5 --target C25 --no-db
```

The `ccf-ai-ab` profile uses OpenAlex only for candidate retrieval. The local
script expands common AI/ReID terms, filters by configured CCF AI A/B venue
aliases, and reports the matched CCF venue/rank in the JSON output.

Restrict to the top three computer-vision conferences, CVPR/ICCV/ECCV:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source openalex --profile ccf-ai-ab --venue-group vision --ccf-rank AB --query "visible infrared person re-identification" --limit 5 --target C25 --no-db
```

Import into the currently selected Zotero collection and attach the PDF:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "attention is all you need" --limit 1 --target C25 --yes
```

The default landing target for script-approved papers is the Zotero candidate
collection `C25`. Use other targets only when you explicitly want to bypass the
candidate review queue. Examples include `L1` for My Library and `C21` for a
read/completed collection:

```powershell
python research-ops\scripts\zotero_local_ingest.py --source arxiv --query "graph neural network" --limit 1 --target C25 --yes --open
```

Notes:

- Zotero Desktop must be open.
- Local imports use `http://127.0.0.1:23119/connector/saveItems` and
  `/connector/saveAttachment`; Zotero's local `/api/` is used only for read-back
  checks.
- OpenAlex records are imported only with a PDF attachment when OpenAlex exposes
  a direct open PDF URL. arXiv usually provides a direct PDF URL.
- If an item already exists in Zotero, the script reuses the existing item unless
  `--force-duplicate` is passed.

For Zotero Web API sync in a later step, configure environment variables:

```powershell
setx ZOTERO_API_KEY "your_zotero_api_key"
setx ZOTERO_USER_ID "your_zotero_user_id"
setx ZOTERO_LIBRARY_TYPE "user"
```

For a group library, use `ZOTERO_GROUP_ID` and set `ZOTERO_LIBRARY_TYPE` to
`group`.

Do not put Zotero keys in `zotero.example.json`, `.env`, reports, or committed
files.

## Paper Digest

Parse Zotero candidate papers into structured local artifacts:

```powershell
python research-ops\scripts\paper_digest.py --title "MambaPro"
```

Search the whole local Zotero library instead of only the candidate collection:

```powershell
python research-ops\scripts\paper_digest.py --title "Learning Progressive Modality-Shared Transformers" --all-zotero
```

Batch parse the most recent candidate papers:

```powershell
python research-ops\scripts\paper_digest.py --limit 5
```

This reads the local Zotero candidate collection, extracts text from available
PDF attachments, and writes:

```text
research-ops/library/parsed/
research-ops/notes/papers/
research-ops/library/kg/
```

For one specific Zotero item:

```powershell
python research-ops\scripts\paper_digest.py --item-key DH67KGHN
```

The parser is read-only with respect to Zotero. It does not edit Zotero items,
annotations, collections, or PDFs.

## Paper Analyzer

For higher-quality long-form paper analysis, prepare a Zotero paper package:

```powershell
python research-ops\scripts\paper_analyzer_prepare.py --title "TVI-LFM" --all-zotero --force
```

The package is written under:

```text
research-ops/analysis/papers/<paper-slug>/
```

It contains:

```text
analysis_input.md
metadata.json
article.md
article.html
```

After writing `article.md`, render HTML with:

```powershell
python .agents\skills\paper-analyzer\scripts\generate_html.py research-ops\analysis\papers\<paper-slug>\article.md research-ops\analysis\papers\<paper-slug>\article.html
```

This workflow is read-only with respect to Zotero. It does not require an extra
API key. If source-code analysis is needed, clone or inspect code only under
`research-ops/tmp/paper-code/`.
