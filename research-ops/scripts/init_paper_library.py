from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = ROOT / "research-ops" / "library"
SCHEMA_PATH = ROOT / "research-ops" / "schemas" / "sqlite-schema.sql"
DB_PATH = LIBRARY_ROOT / "db" / "papers.sqlite"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize the project paper library.")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    for rel in [
        "raw/openalex",
        "raw/arxiv",
        "records",
        "pdf",
        "exports",
        "zotero",
        "logs",
    ]:
        (LIBRARY_ROOT / rel).mkdir(parents=True, exist_ok=True)

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)
        conn.commit()

    print(f"initialized paper library: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
