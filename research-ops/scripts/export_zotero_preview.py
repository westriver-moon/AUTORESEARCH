from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "research-ops" / "library" / "db" / "papers.sqlite"
OUT_PATH = ROOT / "research-ops" / "library" / "zotero" / "zotero-items-preview.json"


def item_type_for_record(record: sqlite3.Row) -> str:
    source = (record["source"] or "").lower()
    if source == "arxiv":
        return "preprint"
    return "journalArticle"


def build_zotero_item(record: sqlite3.Row, authors: list[sqlite3.Row]) -> dict[str, Any]:
    creators = []
    for author in authors:
        name = author["name"]
        if not name:
            continue
        creators.append({"creatorType": "author", "name": name})
    item = {
        "itemType": item_type_for_record(record),
        "title": record["title"],
        "creators": creators,
        "date": record["published_date"] or str(record["year"] or ""),
        "DOI": record["doi"] or "",
        "url": record["url"] or "",
        "abstractNote": record["abstract"] or "",
        "extra": "\n".join(
            part
            for part in [
                f"OpenAlex: {record['openalex_id']}" if record["openalex_id"] else "",
                f"arXiv: {record['arxiv_id']}" if record["arxiv_id"] else "",
                f"PDF: {record['pdf_url']}" if record["pdf_url"] else "",
                f"Canonical ID: {record['canonical_id']}",
            ]
            if part
        ),
    }
    return item


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a Zotero item preview from the paper SQLite library.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--limit", type=int, default=100)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        papers = conn.execute(
            "SELECT * FROM papers ORDER BY published_date DESC, id DESC LIMIT ?",
            (args.limit,),
        ).fetchall()
        items = []
        for paper in papers:
            authors = conn.execute(
                "SELECT * FROM authors WHERE paper_id = ? ORDER BY position ASC",
                (paper["id"],),
            ).fetchall()
            items.append(build_zotero_item(paper, authors))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_database": str(db_path),
        "push_enabled": False,
        "items": items,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote Zotero preview: {out_path}")
    print(f"items: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
