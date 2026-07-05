from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import paper_digest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "research-ops" / "analysis" / "papers"


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return slug[:80] or "paper"


def extract_github_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[^\s)\]]*)?", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        clean = url.rstrip(".,;")
        key = clean.lower()
        if key not in seen:
            deduped.append(clean)
            seen.add(key)
    return deduped


def resolve_items(args: argparse.Namespace) -> tuple[list[dict[str, Any]], str | None]:
    collection_key = args.collection_key or paper_digest.default_collection_key()
    if args.item_key:
        return [paper_digest.zotero_item(key) for key in args.item_key], collection_key
    query = args.title or args.query
    if not query:
        raise RuntimeError("Provide --title, --query, or --item-key.")
    resolver_args = SimpleNamespace(
        title=args.title,
        query=args.query,
        all_zotero=args.all_zotero,
        search_limit=args.search_limit,
        limit=args.limit,
        min_match_score=args.min_match_score,
        allow_multiple=args.allow_multiple,
    )
    try:
        return paper_digest.resolve_items_by_title(resolver_args, collection_key), collection_key
    except Exception as strict_exc:
        if not args.loose_single_match:
            raise
        candidates = paper_digest.zotero_search_items(
            query,
            args.search_limit,
            None if args.all_zotero else collection_key,
        )
        candidates = [
            item
            for item in candidates
            if (item.get("data") or {}).get("itemType") != "attachment"
        ]
        if len(candidates) == 1:
            return candidates, collection_key
        if candidates:
            matches = [
                {
                    "item_key": item.get("key") or (item.get("data") or {}).get("key"),
                    "title": paper_digest.title_for_item(item),
                    "doi": (item.get("data") or {}).get("DOI"),
                }
                for item in candidates[:10]
            ]
            raise RuntimeError(
                "Strict title match failed and loose Zotero search found multiple candidates. "
                "Use --item-key for one item. "
                + json.dumps(matches, ensure_ascii=False)
            ) from strict_exc
        raise


def render_input_markdown(digest: dict[str, Any], full_text: str, github_urls: list[str]) -> str:
    metadata = digest["metadata"]
    zotero = digest["zotero"]
    entities = digest["entities"]
    lines = [
        f"# {digest['title']}",
        "",
        "## Metadata",
        f"- Zotero item key: {zotero['item_key']}",
        f"- DOI: {metadata.get('doi') or 'N/A'}",
        f"- Year/date: {metadata.get('year') or metadata.get('date') or 'N/A'}",
        f"- Venue: {metadata.get('venue') or 'N/A'}",
        f"- Authors: {', '.join(metadata.get('authors') or []) or 'N/A'}",
        f"- URL: {metadata.get('url') or 'N/A'}",
        f"- Local PDF: {digest['pdf'].get('path') or 'No local PDF attachment found'}",
        "",
        "## Detected Project Signals",
        f"- Tasks: {', '.join(entities.get('tasks') or []) or 'N/A'}",
        f"- Datasets: {', '.join(entities.get('datasets') or []) or 'N/A'}",
        f"- Methods: {', '.join(entities.get('methods') or []) or 'N/A'}",
        f"- Metrics: {', '.join(entities.get('metrics') or []) or 'N/A'}",
        "",
        "## Detected GitHub URLs",
    ]
    if github_urls:
        lines.extend(f"- {url}" for url in github_urls)
    else:
        lines.append("- N/A")
    lines.extend(
        [
            "",
            "## Extracted Abstract",
            digest["sections"].get("abstract") or "No abstract extracted.",
            "",
            "## Full Extracted Paper Text",
            "",
            full_text or "No full text extracted.",
            "",
        ]
    )
    return "\n".join(lines)


def write_package(digest: dict[str, Any], full_text: str, output_root: Path, force: bool) -> dict[str, Any]:
    item_key = digest["zotero"]["item_key"]
    base = f"{slugify(digest['title'])}-{item_key}"
    out_dir = output_root / base
    out_dir.mkdir(parents=True, exist_ok=True)
    github_urls = extract_github_urls(full_text + "\n" + json.dumps(digest, ensure_ascii=False))
    paths = {
        "analysis_dir": out_dir,
        "input_markdown": out_dir / "analysis_input.md",
        "metadata_json": out_dir / "metadata.json",
        "article_markdown": out_dir / "article.md",
        "article_html": out_dir / "article.html",
    }
    if not paths["input_markdown"].exists() or force:
        paths["input_markdown"].write_text(render_input_markdown(digest, full_text, github_urls), encoding="utf-8")
    paths["metadata_json"].write_text(
        json.dumps(
            {
                "title": digest["title"],
                "zotero": digest["zotero"],
                "metadata": digest["metadata"],
                "pdf": digest["pdf"],
                "entities": digest["entities"],
                "github_urls": github_urls,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not paths["article_markdown"].exists() or force:
        paths["article_markdown"].write_text(
            "# Draft Placeholder\n\nReplace this file with the paper-analyzer article.\n",
            encoding="utf-8",
        )
    return {key: str(value) for key, value in paths.items()} | {"github_urls": github_urls}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare Zotero paper text for project-local paper-analyzer.")
    parser.add_argument("--title", help="Find one paper by title or partial title.")
    parser.add_argument("--query", help="Alias for --title.")
    parser.add_argument("--item-key", action="append", default=[], help="Specific Zotero item key. Can be repeated.")
    parser.add_argument("--all-zotero", action="store_true", help="Search the whole local Zotero library.")
    parser.add_argument("--collection-key", help="Candidate collection key. Defaults to library.json.")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--search-limit", type=int, default=25)
    parser.add_argument("--min-match-score", type=int, default=45)
    parser.add_argument("--allow-multiple", action="store_true")
    parser.add_argument(
        "--no-loose-single-match",
        dest="loose_single_match",
        action="store_false",
        help="Disable fallback to a single Zotero full-text search hit.",
    )
    parser.set_defaults(loose_single_match=True)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        output_root = Path(args.output_root).expanduser().resolve()
        items, collection_key = resolve_items(args)
        outputs = []
        for item in items:
            digest = paper_digest.digest_item(item, max_pages=args.max_pages)
            full_text = digest.pop("_text", "")
            outputs.append(
                {
                    "title": digest["title"],
                    "zotero_item_key": digest["zotero"]["item_key"],
                    "has_pdf": bool(digest["pdf"].get("path")),
                    "text_chars": len(full_text),
                    "package": write_package(digest, full_text, output_root, args.force),
                }
            )
        print(
            json.dumps(
                {
                    "ok": True,
                    "collection_key": collection_key,
                    "items_seen": len(items),
                    "outputs": outputs,
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
