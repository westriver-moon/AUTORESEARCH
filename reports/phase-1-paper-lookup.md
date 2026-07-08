# Phase 1 Paper Lookup Report

## Summary

Status: PASS with one external validation caveat.

`paper-lookup` was installed as a project-local Codex Skill. The installed
Skill is Markdown/reference only, with no scripts, no project-code mutation
logic, and no SSH/GPU/training integration. Minimal live retrieval succeeded
against arXiv, OpenAlex, and Crossref. Semantic Scholar failed twice with HTTP
429 from the anonymous shared rate pool.

## Provenance

| Field | Value |
|---|---|
| Source repository | `https://github.com/K-Dense-AI/scientific-agent-skills.git` |
| Source directory | `skills/paper-lookup/` |
| Commit SHA | `1e024ea8547ada12039edbe8197aaa959d97763f` |
| License | MIT License, copyright 2025 K-Dense Inc. |
| Install path | `.agents/skills/paper-lookup/` |

Installed files:

```text
.agents/skills/paper-lookup/SKILL.md
.agents/skills/paper-lookup/references/arxiv.md
.agents/skills/paper-lookup/references/biorxiv.md
.agents/skills/paper-lookup/references/core.md
.agents/skills/paper-lookup/references/crossref.md
.agents/skills/paper-lookup/references/medrxiv.md
.agents/skills/paper-lookup/references/openalex.md
.agents/skills/paper-lookup/references/pmc.md
.agents/skills/paper-lookup/references/pubmed.md
.agents/skills/paper-lookup/references/semantic-scholar.md
.agents/skills/paper-lookup/references/unpaywall.md
```

No other Skill from `K-Dense-AI/scientific-agent-skills` was installed.

## Codex Discovery

Static project-level discovery check: pass.

Evidence:

```text
.agents/skills/paper-lookup/SKILL.md exists
SKILL.md declares: name: paper-lookup
```

CLI discovery check: blocked by local WindowsApps execution permission, not by
the Skill layout.

Attempted command:

```powershell
codex debug prompt-input '$paper-lookup test'
```

Result:

```text
Program 'codex.exe' failed to run: Access is denied
```

Current Codex sessions may not hot-load newly installed project Skills. A reload
or new Codex App session is expected before UI-level discovery can be confirmed.

## Compatibility Review

Linux-only commands: no hard dependency found.

The Skill documentation mentions `curl via Bash` as a fallback for some
platforms. On Windows this can be replaced by PowerShell, Python `urllib`, or
Windows `curl.exe`; the Skill itself ships no shell scripts.

Windows path issues: no blocking issue found.

The installed Skill contains only Markdown files and relative references such as
`references/arxiv.md`. No `/home`, SSH path, GPU path, or hardcoded project path
dependency was found.

API keys:

| Source | Key / Contact | Required for Phase 1? | Notes |
|---|---|---:|---|
| arXiv | None | No | Public Atom XML API. |
| OpenAlex | `OPENALEX_API_KEY` | No | Recommended for higher limits; unauthenticated test passed. |
| Crossref | `mailto` / contact email | No | Recommended for polite pool; unauthenticated test passed. |
| Semantic Scholar | `S2_API_KEY` | No, but recommended | Anonymous shared pool returned HTTP 429 twice. |
| PubMed / PMC | `NCBI_API_KEY` | No | Optional; not tested in this phase. |
| CORE | `CORE_API_KEY` | Yes for full text | Not tested in this phase. |
| Unpaywall | real email parameter | Yes for lookup | Not tested in this phase. |

Environment variables checked and absent:

```text
NCBI_API_KEY
CORE_API_KEY
S2_API_KEY
OPENALEX_API_KEY
UNPAYWALL_EMAIL
CROSSREF_MAILTO
```

Project modification risk: low.

The Skill instructs the agent to call REST APIs and return results. It does not
instruct creating a paper database, editing source code, installing Zotero,
connecting SSH, using GPU, starting training, or invoking
`codex-autoresearch-v2`.

## Minimal Retrieval Tests

All raw responses were written only to a temporary directory:

```text
C:\Users\pbrii\AppData\Local\Temp\paper_lookup_phase1_5vo3rs1m
```

Summary file:

```text
C:\Users\pbrii\AppData\Local\Temp\paper_lookup_phase1_5vo3rs1m\summary.json
```

| Source | Keyword | Result | Status | Raw file |
|---|---|---:|---:|---|
| arXiv | `transformer attention` | Success | 200 | `01_arxiv.xml` |
| OpenAlex | `graph neural networks` | Success | 200 | `02_openalex.json` |
| Crossref | `protein structure prediction` | Success | 200 | `03_crossref.json` |
| Semantic Scholar | `large language models` | Failed | 429 | `04_semantic_scholar_error.txt` |
| Semantic Scholar retry | `large language models` | Failed | 429 | `04b_semantic_scholar_retry_error.txt` |

Successful source details:

| Source | Count hint | Sample titles |
|---|---:|---|
| arXiv | 17,783 | `Dilated Neighborhood Attention Transformer`; `Energy-Gated Attention and Wavelet Positional Encoding: Complementary Inductive Biases for Transformer Attention` |
| OpenAlex | 803,062 | `The Graph Neural Network Model`; `A Comprehensive Survey on Graph Neural Networks` |
| Crossref | 4,050,142 | `2010/06/08: Protein Prediction: lecture 11: Protein Structure Prediction CM: Burkhard Rost`; `20110517 - Protein Prediction I - Protein Structure - Burkhard Rost` |

Failed source details:

| Source | Reason | Likely fix |
|---|---|---|
| Semantic Scholar | HTTP 429 from anonymous shared rate pool, repeated after one retry. | Set `S2_API_KEY` or retry later. |

## Phase 2 Recommendation

Recommended to enter Phase 2, with two caveats:

1. Reload or reopen Codex App before relying on UI-level `$paper-lookup`
   discovery.
2. If Semantic Scholar is important, configure `S2_API_KEY`; otherwise use
   arXiv, OpenAlex, and Crossref as the initial no-key retrieval path.

No Zotero dependency, paper database, `research-ops`, SSH connection,
`codex-autoresearch-v2`, GPU training, or formal literature store was created in
Phase 1.

## Verdict

PHASE 1 PASSED
