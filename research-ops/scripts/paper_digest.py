from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "research-ops" / "config" / "library.json"
DEFAULT_PARSED_ROOT = ROOT / "research-ops" / "library" / "parsed"
DEFAULT_NOTES_ROOT = ROOT / "research-ops" / "notes" / "papers"
DEFAULT_KG_ROOT = ROOT / "research-ops" / "library" / "kg"
ZOTERO_BASE = "http://127.0.0.1:23119"
CONNECTOR_API_VERSION = "3"


DATASET_TERMS = [
    "SYSU-MM01",
    "RegDB",
    "LLCM",
    "VCM",
    "Market-1501",
    "DukeMTMC-reID",
    "MSMT17",
    "CUHK-PEDES",
    "RGBNT201",
    "RGBNT100",
    "MSVR310",
]
METHOD_TERMS = [
    "PMT",
    "Transformer",
    "Vision Transformer",
    "CLIP",
    "Mamba",
    "Diffusion",
    "Mixture of Experts",
    "MoE",
    "Token",
    "Prompt",
    "Contrastive",
    "Cross-modal",
    "Cross-modality",
    "Modality",
    "Attention",
]
METRIC_TERMS = ["Rank-1", "Rank 1", "mAP", "mINP", "CMC"]
TASK_TERMS = [
    "visible-infrared person re-identification",
    "VI-ReID",
    "cross-modality person re-identification",
    "person re-identification",
    "object re-identification",
    "multi-modal object re-identification",
]


class PaperDigestError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return slug[:80] or "paper"


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_query_text(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text or "", flags=re.I).strip().casefold()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def default_collection_key() -> str:
    config = load_config()
    key = (
        (config.get("zotero_local_targets") or {})
        .get("candidate_collection", {})
        .get("collection_key")
    )
    if not key:
        raise PaperDigestError("Missing candidate collection key in research-ops/config/library.json.")
    return str(key)


def zotero_json(path: str, *, timeout: int = 30) -> Any:
    request = urllib.request.Request(
        ZOTERO_BASE + path,
        headers={"X-Zotero-Connector-API-Version": CONNECTOR_API_VERSION},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else None
    except Exception as exc:  # urllib uses several platform-specific exception chains on Windows.
        raise PaperDigestError("Zotero local API is not reachable. Open Zotero Desktop first.") from exc


def zotero_items_from_collection(collection_key: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"sort": "dateModified", "direction": "desc", "limit": str(limit)})
    data = zotero_json(f"/api/users/0/collections/{collection_key}/items/top?{query}")
    return data if isinstance(data, list) else []


def zotero_search_items(query_text: str, limit: int, collection_key: str | None) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"q": query_text, "qmode": "everything", "limit": str(limit)})
    if collection_key:
        path = f"/api/users/0/collections/{collection_key}/items/top?{query}"
    else:
        path = f"/api/users/0/items/top?{query}"
    data = zotero_json(path)
    return data if isinstance(data, list) else []


def zotero_item(item_key: str) -> dict[str, Any]:
    data = zotero_json(f"/api/users/0/items/{item_key}")
    if not isinstance(data, dict):
        raise PaperDigestError(f"Unexpected Zotero response for item {item_key}.")
    return data


def zotero_children(item_key: str) -> list[dict[str, Any]]:
    data = zotero_json(f"/api/users/0/items/{item_key}/children")
    return data if isinstance(data, list) else []


def file_url_to_path(url: str | None) -> Path | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "file":
        return None
    path = urllib.parse.unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return Path(path)


def first_pdf_attachment(item_key: str) -> tuple[dict[str, Any] | None, Path | None]:
    for child in zotero_children(item_key):
        data = child.get("data") or {}
        if data.get("itemType") != "attachment" or data.get("contentType") != "application/pdf":
            continue
        enclosure = ((child.get("links") or {}).get("enclosure") or {}).get("href")
        path = file_url_to_path(enclosure)
        return child, path if path and path.exists() else None
    return None, None


def creator_names(data: dict[str, Any]) -> list[str]:
    names = []
    for creator in data.get("creators") or []:
        first = creator.get("firstName") or ""
        last = creator.get("lastName") or ""
        name = normalize_space(f"{first} {last}") or creator.get("name")
        if name:
            names.append(name)
    return names


def title_for_item(item: dict[str, Any]) -> str:
    return ((item.get("data") or {}).get("title") or item.get("title") or "").strip()


def score_title_match(query_text: str, item: dict[str, Any]) -> tuple[int, int, int]:
    title = title_for_item(item)
    normalized_query = normalize_query_text(query_text)
    normalized_title = normalize_query_text(title)
    if not normalized_query or not normalized_title:
        return (0, 0, 0)
    if normalized_query == normalized_title:
        return (1000, len(normalized_query), len(normalized_title))
    if normalized_query in normalized_title:
        return (900, len(normalized_query), -len(normalized_title))
    tokens = [token for token in normalized_query.split() if len(token) > 1]
    title_tokens = set(normalized_title.split())
    matched = sum(1 for token in tokens if token in title_tokens)
    coverage = int((matched / max(1, len(tokens))) * 100)
    return (coverage, matched, -len(normalized_title))


def resolve_items_by_title(args: argparse.Namespace, collection_key: str | None) -> list[dict[str, Any]]:
    title_queries = [value for value in [args.title, args.query] if value]
    if not title_queries:
        return []
    query_text = title_queries[0]
    search_limit = max(args.search_limit, args.limit, 10)
    candidates = zotero_search_items(query_text, search_limit, None if args.all_zotero else collection_key)
    if not candidates and collection_key and not args.all_zotero:
        raise PaperDigestError(
            f"No Zotero items matched title query {query_text!r} in the candidate collection. "
            "Use --all-zotero to search the whole local Zotero library."
        )
    scored = [
        (score_title_match(query_text, item), item)
        for item in candidates
        if (item.get("data") or {}).get("itemType") != "attachment"
    ]
    scored = [(score, item) for score, item in scored if score[0] >= args.min_match_score]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if not scored:
        raise PaperDigestError(f"No sufficiently close Zotero title match for {query_text!r}.")
    best_score = scored[0][0][0]
    close_matches = [(score, item) for score, item in scored if best_score - score[0] <= 8]
    if len(close_matches) > 1 and not args.allow_multiple:
        matches = [
            {
                "item_key": item.get("key") or (item.get("data") or {}).get("key"),
                "title": title_for_item(item),
                "score": score[0],
                "doi": (item.get("data") or {}).get("DOI"),
            }
            for score, item in close_matches[:10]
        ]
        raise PaperDigestError(
            "Multiple close Zotero title matches. Re-run with --item-key for one item or --allow-multiple. "
            + json.dumps(matches, ensure_ascii=False)
        )
    selected = [item for _, item in (scored[: args.limit] if args.allow_multiple else scored[:1])]
    return selected


def extract_text_with_pypdf(path: Path, max_pages: int) -> tuple[str, dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    total_pages = len(reader.pages)
    for page in reader.pages[: min(max_pages, total_pages)]:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages), {"backend": "pypdf", "total_pages": total_pages, "pages_extracted": len(pages)}


def extract_text_with_pymupdf(path: Path, max_pages: int) -> tuple[str, dict[str, Any]]:
    import fitz

    doc = fitz.open(str(path))
    pages = []
    total_pages = doc.page_count
    for index in range(min(max_pages, total_pages)):
        pages.append(doc.load_page(index).get_text("text"))
    doc.close()
    return "\n\n".join(pages), {"backend": "pymupdf", "total_pages": total_pages, "pages_extracted": len(pages)}


def extract_pdf_text(path: Path, max_pages: int) -> tuple[str, dict[str, Any]]:
    try:
        return extract_text_with_pypdf(path, max_pages)
    except Exception as first_exc:
        try:
            text, meta = extract_text_with_pymupdf(path, max_pages)
            meta["fallback_reason"] = f"pypdf failed: {type(first_exc).__name__}: {first_exc}"
            return text, meta
        except Exception as second_exc:
            raise PaperDigestError(
                f"Could not extract text from {path}: pypdf={first_exc}; pymupdf={second_exc}"
            ) from second_exc


def find_terms(text: str, terms: list[str]) -> list[str]:
    found = []
    haystack = text.casefold()
    for term in terms:
        if term.casefold() in haystack:
            found.append(term)
    return found


def snippet_around(text: str, pattern: str, *, chars: int = 1400) -> str:
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return ""
    start = max(0, match.start() - chars // 4)
    end = min(len(text), match.end() + chars)
    return normalize_space(text[start:end])


def first_abstract(text: str, fallback: str | None) -> str:
    if fallback:
        return normalize_space(fallback)
    snippet = snippet_around(text, r"\babstract\b", chars=1800)
    if not snippet:
        return ""
    snippet = re.sub(r"^.*?\babstract\b[:\s-]*", "", snippet, flags=re.I)
    return normalize_space(snippet)[:1800]


def build_relation_summary(title: str, text: str, entities: dict[str, list[str]]) -> list[str]:
    combined = f"{title}\n{text[:10000]}"
    lower = combined.casefold()
    reasons = []
    if "visible-infrared" in lower or "visible infrared" in lower or "vi-reid" in lower:
        reasons.append("Directly matches visible-infrared / VI-ReID.")
    if "cross-modality" in lower or "cross-modal" in lower:
        reasons.append("Targets cross-modality representation or matching.")
    if "sysu-mm01" in lower:
        reasons.append("Mentions SYSU-MM01, the current server baseline dataset.")
    if "pmt" in lower or "progressive modality-shared" in lower:
        reasons.append("Connects to PMT-style modality-shared transformer baselines.")
    if any(term in entities["methods"] for term in ["CLIP", "Mamba", "Diffusion", "Transformer"]):
        reasons.append("Contains modern model components relevant to current ReID exploration.")
    return reasons or ["Potentially related to ReID; manual screening is recommended."]


def graph_for_digest(digest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    item_key = digest["zotero"]["item_key"]
    paper_id = f"paper:{item_key}"
    nodes = [
        {
            "id": paper_id,
            "type": "paper",
            "label": digest["title"],
            "zotero_item_key": item_key,
            "doi": digest["metadata"].get("doi"),
            "year": digest["metadata"].get("year"),
        }
    ]
    edges = []
    venue = digest["metadata"].get("venue")
    if venue:
        venue_id = f"venue:{venue}"
        nodes.append({"id": venue_id, "type": "venue", "label": venue})
        edges.append({"source": paper_id, "target": venue_id, "type": "published_in"})
    for category, edge_type in [
        ("datasets", "uses_dataset"),
        ("methods", "uses_method_signal"),
        ("metrics", "reports_metric"),
        ("tasks", "addresses_task"),
    ]:
        for value in digest["entities"].get(category, []):
            node_id = f"{category[:-1]}:{value}"
            nodes.append({"id": node_id, "type": category[:-1], "label": value})
            edges.append({"source": paper_id, "target": node_id, "type": edge_type})
    return nodes, edges


def render_note(digest: dict[str, Any]) -> str:
    metadata = digest["metadata"]
    zotero = digest["zotero"]
    entities = digest["entities"]
    lines = [
        "---",
        f"zotero_item_key: {zotero['item_key']}",
        f"doi: {metadata.get('doi') or ''}",
        f"year: {metadata.get('year') or ''}",
        f"generated_at: {digest['generated_at']}",
        "---",
        "",
        f"# {digest['title']}",
        "",
        "## Metadata",
        f"- Zotero item: zotero://select/library/items/{zotero['item_key']}",
        f"- DOI: {metadata.get('doi') or 'N/A'}",
        f"- Year/date: {metadata.get('year') or metadata.get('date') or 'N/A'}",
        f"- Venue: {metadata.get('venue') or 'N/A'}",
        f"- Authors: {', '.join(metadata.get('authors') or []) or 'N/A'}",
        f"- PDF: {digest['pdf'].get('path') or 'No local PDF attachment found'}",
        "",
        "## Why It Matters For This Project",
    ]
    lines.extend(f"- {reason}" for reason in digest["project_relevance"])
    lines.extend(
        [
            "",
            "## One-Pass Reading Card",
            "- Research problem: TODO",
            "- Core idea: TODO",
            "- Architecture/module changes: TODO",
            "- Datasets/protocol: TODO",
            "- Main metrics: TODO",
            "- Difference from PMT / current baseline: TODO",
            "- Reproducible experiment idea: TODO",
            "- Keep / move / discard decision: TODO",
            "",
            "## Extracted Abstract",
            digest["sections"].get("abstract") or "No abstract extracted.",
            "",
            "## Extracted Method Signal",
            digest["sections"].get("method") or "No method-like snippet extracted.",
            "",
            "## Extracted Experiment Signal",
            digest["sections"].get("experiment") or "No experiment-like snippet extracted.",
            "",
            "## Detected Entities",
            f"- Tasks: {', '.join(entities['tasks']) or 'N/A'}",
            f"- Datasets: {', '.join(entities['datasets']) or 'N/A'}",
            f"- Methods: {', '.join(entities['methods']) or 'N/A'}",
            f"- Metrics: {', '.join(entities['metrics']) or 'N/A'}",
            "",
            "## Manual Notes",
            "- [ ] Confirm relevance.",
            "- [ ] Mark key figures/tables in Zotero.",
            "- [ ] Move accepted papers out of the candidate collection.",
            "",
        ]
    )
    return "\n".join(lines)


def digest_item(item: dict[str, Any], *, max_pages: int) -> dict[str, Any]:
    data = item.get("data") or {}
    item_key = item.get("key") or data.get("key")
    if not item_key:
        raise PaperDigestError("Zotero item without key.")
    attachment, pdf_path = first_pdf_attachment(item_key)
    text = ""
    extraction: dict[str, Any] = {"backend": None, "total_pages": 0, "pages_extracted": 0}
    if pdf_path:
        text, extraction = extract_pdf_text(pdf_path, max_pages)
    title = data.get("title") or "Untitled"
    combined = f"{title}\n{data.get('abstractNote') or ''}\n{text}"
    entities = {
        "tasks": find_terms(combined, TASK_TERMS),
        "datasets": find_terms(combined, DATASET_TERMS),
        "methods": find_terms(combined, METHOD_TERMS),
        "metrics": find_terms(combined, METRIC_TERMS),
    }
    metadata = {
        "doi": data.get("DOI"),
        "year": (data.get("date") or "")[:4],
        "date": data.get("date"),
        "venue": data.get("publicationTitle") or data.get("conferenceName"),
        "authors": creator_names(data),
        "url": data.get("url"),
        "item_type": data.get("itemType"),
    }
    sections = {
        "abstract": first_abstract(text, data.get("abstractNote")),
        "method": snippet_around(text, r"\b(method|approach|framework|architecture|model)\b"),
        "experiment": snippet_around(text, r"\b(experiment|evaluation|dataset|results?|rank-?1|mAP|mINP)\b"),
    }
    return {
        "generated_at": utc_now(),
        "title": title,
        "metadata": metadata,
        "zotero": {
            "item_key": item_key,
            "collection_keys": data.get("collections") or [],
            "attachment_key": attachment.get("key") if attachment else None,
        },
        "pdf": {
            "path": str(pdf_path) if pdf_path else None,
            "attachment_title": ((attachment or {}).get("data") or {}).get("title"),
            **extraction,
            "text_chars": len(text),
        },
        "sections": sections,
        "entities": entities,
        "project_relevance": build_relation_summary(title, combined, entities),
        "raw_text_available": bool(text),
        "_text": text,
    }


def write_digest(
    digest: dict[str, Any],
    *,
    parsed_root: Path,
    notes_root: Path,
    force: bool,
) -> dict[str, str]:
    parsed_root.mkdir(parents=True, exist_ok=True)
    notes_root.mkdir(parents=True, exist_ok=True)
    item_key = digest["zotero"]["item_key"]
    base = f"{slugify(digest['title'])}-{item_key}"
    json_path = parsed_root / f"{base}.json"
    text_path = parsed_root / f"{base}.txt"
    note_path = notes_root / f"{base}.md"
    if not force and (json_path.exists() or note_path.exists()):
        return {
            "status": "exists",
            "json_path": str(json_path),
            "text_path": str(text_path),
            "note_path": str(note_path),
        }
    text = digest.pop("_text", "")
    json_path.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    if text:
        text_path.write_text(text, encoding="utf-8")
    note_path.write_text(render_note(digest), encoding="utf-8")
    return {
        "status": "written",
        "json_path": str(json_path),
        "text_path": str(text_path) if text else "",
        "note_path": str(note_path),
    }


def rebuild_graph(parsed_root: Path, kg_root: Path) -> dict[str, Any]:
    kg_root.mkdir(parents=True, exist_ok=True)
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edge_keys: set[tuple[str, str, str]] = set()
    edges: list[dict[str, Any]] = []
    for path in sorted(parsed_root.glob("*.json")):
        digest = json.loads(path.read_text(encoding="utf-8"))
        nodes, digest_edges = graph_for_digest(digest)
        for node in nodes:
            nodes_by_id[node["id"]] = node
        for edge in digest_edges:
            key = (edge["source"], edge["target"], edge["type"])
            if key not in edge_keys:
                edges.append(edge)
                edge_keys.add(key)
    graph = {
        "generated_at": utc_now(),
        "nodes": sorted(nodes_by_id.values(), key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["source"], item["type"], item["target"])),
    }
    (kg_root / "paper_graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (kg_root / "nodes.jsonl").write_text(
        "\n".join(json.dumps(node, ensure_ascii=False) for node in graph["nodes"]) + "\n",
        encoding="utf-8",
    )
    (kg_root / "edges.jsonl").write_text(
        "\n".join(json.dumps(edge, ensure_ascii=False) for edge in graph["edges"]) + "\n",
        encoding="utf-8",
    )
    return {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "path": str(kg_root / "paper_graph.json")}


def write_index(notes_root: Path) -> str:
    notes = sorted(notes_root.glob("*.md"))
    lines = ["# Paper Notes Index", "", f"Generated at: {utc_now()}", ""]
    for note in notes:
        if note.name == "index.md":
            continue
        lines.append(f"- [{note.stem}]({note.name})")
    index_path = notes_root / "index.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(index_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse local Zotero paper PDFs into structured JSON, reading notes, and a lightweight graph."
    )
    parser.add_argument("--collection-key", default=None, help="Zotero collection key. Defaults to candidate collection.")
    parser.add_argument("--item-key", action="append", default=[], help="Specific Zotero item key. Can be repeated.")
    parser.add_argument("--title", help="Find one paper by title or partial title in the candidate collection.")
    parser.add_argument("--query", help="Alias for --title.")
    parser.add_argument("--all-zotero", action="store_true", help="Search the whole local Zotero library instead of only the candidate collection.")
    parser.add_argument("--search-limit", type=int, default=25, help="Maximum Zotero search candidates to inspect.")
    parser.add_argument("--min-match-score", type=int, default=45, help="Minimum fuzzy title match score.")
    parser.add_argument("--allow-multiple", action="store_true", help="Digest multiple matching title results instead of requiring a single best match.")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent collection items to process.")
    parser.add_argument("--max-pages", type=int, default=8, help="Maximum PDF pages to extract per paper.")
    parser.add_argument("--parsed-root", default=str(DEFAULT_PARSED_ROOT))
    parser.add_argument("--notes-root", default=str(DEFAULT_NOTES_ROOT))
    parser.add_argument("--kg-root", default=str(DEFAULT_KG_ROOT))
    parser.add_argument("--force", action="store_true", help="Overwrite existing parsed JSON and notes.")
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        parsed_root = Path(args.parsed_root).expanduser().resolve()
        notes_root = Path(args.notes_root).expanduser().resolve()
        kg_root = Path(args.kg_root).expanduser().resolve()
        collection_key = args.collection_key or default_collection_key()
        if args.item_key:
            items = [zotero_item(key) for key in args.item_key]
            source_mode = "item-key"
        elif args.title or args.query:
            items = resolve_items_by_title(args, collection_key)
            source_mode = "title"
        else:
            items = zotero_items_from_collection(collection_key, args.limit)
            source_mode = "collection"
        outputs = []
        for item in items:
            digest = digest_item(item, max_pages=args.max_pages)
            outputs.append(
                {
                    "title": digest["title"],
                    "zotero_item_key": digest["zotero"]["item_key"],
                    "has_pdf": bool(digest["pdf"].get("path")),
                    "text_chars": digest["pdf"].get("text_chars", 0),
                    "entities": digest["entities"],
                    **write_digest(digest, parsed_root=parsed_root, notes_root=notes_root, force=args.force),
                }
            )
        graph = rebuild_graph(parsed_root, kg_root)
        index_path = write_index(notes_root)
        print(
            json.dumps(
                {
                    "ok": True,
                    "collection_key": collection_key,
                    "source_mode": source_mode,
                    "items_seen": len(items),
                    "outputs": outputs,
                    "graph": graph,
                    "index_path": index_path,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
