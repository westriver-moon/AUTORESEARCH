from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = ROOT / "research-ops" / "library"
DB_PATH = LIBRARY_ROOT / "db" / "papers.sqlite"
USER_AGENT = "Codex research-ops paper lookup/1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower()
    return slug[:80] or "query"


def fetch(url: str, *, accept: str = "*/*", timeout: int = 60) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.URLError:
        if not shutil.which("curl.exe"):
            raise
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            completed = subprocess.run(
                [
                    "curl.exe",
                    "--http1.1",
                    "--location",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    str(timeout),
                    "--user-agent",
                    USER_AGENT,
                    "--write-out",
                    "%{http_code}",
                    "--output",
                    str(tmp_path),
                    url,
                ],
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise urllib.error.URLError(completed.stderr.strip() or "curl fallback failed")
            status_text = completed.stdout.strip() or "0"
            return int(status_text), tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)


def redact_endpoint(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [(key, value) for key, value in query if key.lower() != "api_key"]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(redacted), parsed.fragment)
    )


def canonical_id(record: dict[str, Any]) -> str:
    for key in ("doi", "arxiv_id", "openalex_id"):
        value = record.get(key)
        if value:
            return f"{key}:{str(value).lower()}"
    digest = hashlib.sha256(record["title"].encode("utf-8")).hexdigest()[:16]
    return f"title_hash:{digest}"


def openalex_url(query: str, limit: int, since: str, until: str | None, title_only: bool) -> str:
    filters = [f"from_publication_date:{since}", "type:article"]
    if until:
        filters.append(f"to_publication_date:{until}")
    if title_only:
        filters.append(f"title.search:{query}")
        params = {
            "filter": ",".join(filters),
            "sort": "publication_date:desc",
            "per_page": str(limit),
            "select": "id,doi,title,publication_year,publication_date,type,cited_by_count,authorships,open_access,primary_location",
        }
    else:
        params = {
            "search": query,
            "filter": ",".join(filters),
            "sort": "publication_date:desc",
            "per_page": str(limit),
            "select": "id,doi,title,publication_year,publication_date,type,cited_by_count,authorships,open_access,primary_location",
        }
    api_key = os.environ.get("OPENALEX_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return "https://api.openalex.org/works?" + urllib.parse.urlencode(params)


def parse_openalex(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        authors = []
        for authorship in item.get("authorships") or []:
            author = (authorship or {}).get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(
                    {
                        "name": name,
                        "orcid": author.get("orcid"),
                        "metadata": authorship,
                    }
                )
        location = item.get("primary_location") or {}
        source = (location.get("source") or {}).get("display_name")
        doi = item.get("doi")
        open_access = item.get("open_access") or {}
        record = {
            "title": item.get("title") or "Untitled",
            "year": item.get("publication_year"),
            "published_date": item.get("publication_date"),
            "doi": doi,
            "arxiv_id": None,
            "openalex_id": item.get("id"),
            "source": source,
            "url": doi or item.get("id"),
            "pdf_url": location.get("pdf_url") or open_access.get("oa_url"),
            "abstract": None,
            "authors": authors,
            "identifiers": {
                "doi": doi,
                "openalex": item.get("id"),
            },
            "metadata": item,
        }
        record["canonical_id"] = canonical_id(record)
        records.append(record)
    return records


def arxiv_url(query: str, limit: int) -> str:
    title_query = f'ti:"{query}"'
    params = {
        "search_query": title_query,
        "start": "0",
        "max_results": str(limit),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)


def parse_arxiv(raw: bytes) -> tuple[int | None, list[dict[str, Any]]]:
    root = ET.fromstring(raw)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    total_text = root.findtext("opensearch:totalResults", namespaces=ns)
    total = int(total_text) if total_text and total_text.isdigit() else None
    records: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        entry_id = entry.findtext("atom:id", namespaces=ns)
        arxiv_id = None
        if entry_id:
            arxiv_id = entry_id.rstrip("/").split("/")[-1].split("v")[0]
        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href")
        authors = [
            {"name": a.findtext("atom:name", default="", namespaces=ns), "orcid": None, "metadata": {}}
            for a in entry.findall("atom:author", ns)
        ]
        record = {
            "title": " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split()) or "Untitled",
            "year": int((entry.findtext("atom:published", default="", namespaces=ns) or "0000")[:4] or 0) or None,
            "published_date": (entry.findtext("atom:published", namespaces=ns) or "")[:10] or None,
            "doi": entry.findtext("arxiv:doi", namespaces=ns),
            "arxiv_id": arxiv_id,
            "openalex_id": None,
            "source": "arXiv",
            "url": entry_id,
            "pdf_url": pdf_url,
            "abstract": " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split()),
            "authors": authors,
            "identifiers": {"arxiv": arxiv_id},
            "metadata": {
                "id": entry_id,
                "updated": entry.findtext("atom:updated", namespaces=ns),
                "primary_category": (
                    entry.find("arxiv:primary_category", ns).attrib.get("term")
                    if entry.find("arxiv:primary_category", ns) is not None
                    else None
                ),
            },
        }
        record["canonical_id"] = canonical_id(record)
        records.append(record)
    return total, records


def write_retrieval(
    conn: sqlite3.Connection,
    *,
    source: str,
    query: str,
    endpoint: str,
    status_code: int | None,
    raw_path: Path | None,
    result_count: int | None,
    error: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO retrievals(source, query, endpoint, fetched_at, status_code, raw_path, result_count, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (source, query, endpoint, utc_now(), status_code, str(raw_path) if raw_path else None, result_count, error),
    )


def upsert_records(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> int:
    written = 0
    for record in records:
        now = utc_now()
        metadata_json = json.dumps(record["metadata"], ensure_ascii=False, sort_keys=True)
        conn.execute(
            """
            INSERT INTO papers(
              canonical_id, title, year, published_date, doi, arxiv_id, openalex_id,
              source, url, pdf_url, abstract, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_id) DO UPDATE SET
              title=excluded.title,
              year=excluded.year,
              published_date=excluded.published_date,
              doi=excluded.doi,
              arxiv_id=excluded.arxiv_id,
              openalex_id=excluded.openalex_id,
              source=excluded.source,
              url=excluded.url,
              pdf_url=excluded.pdf_url,
              abstract=excluded.abstract,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
            """,
            (
                record["canonical_id"],
                record["title"],
                record.get("year"),
                record.get("published_date"),
                record.get("doi"),
                record.get("arxiv_id"),
                record.get("openalex_id"),
                record.get("source"),
                record.get("url"),
                record.get("pdf_url"),
                record.get("abstract"),
                metadata_json,
                now,
                now,
            ),
        )
        paper_id = conn.execute(
            "SELECT id FROM papers WHERE canonical_id = ?", (record["canonical_id"],)
        ).fetchone()[0]
        conn.execute("DELETE FROM authors WHERE paper_id = ?", (paper_id,))
        for pos, author in enumerate(record.get("authors") or [], start=1):
            conn.execute(
                """
                INSERT INTO authors(paper_id, position, name, orcid, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    paper_id,
                    pos,
                    author.get("name") or "",
                    author.get("orcid"),
                    json.dumps(author.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        for id_type, value in (record.get("identifiers") or {}).items():
            if value:
                conn.execute(
                    "INSERT OR IGNORE INTO identifiers(paper_id, id_type, value) VALUES (?, ?, ?)",
                    (paper_id, id_type, value),
                )
        written += 1
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lookup papers and optionally write them to the project library.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--source", choices=["openalex", "arxiv", "all"], default="openalex")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--since", default="2025-01-01")
    parser.add_argument("--until")
    parser.add_argument("--title-only", action="store_true")
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--db", default=str(DB_PATH))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    sources = ["openalex", "arxiv"] if args.source == "all" else [args.source]
    db_path = Path(args.db).expanduser().resolve()
    raw_summary: dict[str, Any] = {"query": args.query, "sources": {}}
    conn = sqlite3.connect(db_path) if args.write_db else None
    try:
        for source in sources:
            endpoint = openalex_url(args.query, args.limit, args.since, args.until, args.title_only) if source == "openalex" else arxiv_url(args.query, args.limit)
            raw_dir = LIBRARY_ROOT / "raw" / source
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{slugify(args.query)}.{ 'json' if source == 'openalex' else 'xml' }"
            try:
                status, raw = fetch(endpoint, accept="application/json" if source == "openalex" else "*/*")
                raw_path.write_bytes(raw)
                if source == "openalex":
                    payload = json.loads(raw.decode("utf-8"))
                    records = parse_openalex(payload)
                    result_count = (payload.get("meta") or {}).get("count")
                else:
                    result_count, records = parse_arxiv(raw)
                if conn:
                    write_retrieval(
                        conn,
                        source=source,
                        query=args.query,
                        endpoint=redact_endpoint(endpoint),
                        status_code=status,
                        raw_path=raw_path,
                        result_count=result_count,
                        error=None,
                    )
                    upsert_records(conn, records)
                    conn.commit()
                raw_summary["sources"][source] = {
                    "ok": True,
                    "status": status,
                    "endpoint": redact_endpoint(endpoint),
                    "raw_path": str(raw_path),
                    "result_count": result_count,
                    "records": [
                        {
                            "title": r["title"],
                            "published_date": r.get("published_date"),
                            "doi": r.get("doi"),
                            "arxiv_id": r.get("arxiv_id"),
                            "openalex_id": r.get("openalex_id"),
                            "url": r.get("url"),
                        }
                        for r in records
                    ],
                }
            except urllib.error.HTTPError as exc:
                body = exc.read()
                raw_path.write_bytes(body)
                error = f"HTTP {exc.code}: {exc.reason}"
                if conn:
                    write_retrieval(
                        conn,
                        source=source,
                        query=args.query,
                        endpoint=redact_endpoint(endpoint),
                        status_code=exc.code,
                        raw_path=raw_path,
                        result_count=None,
                        error=error,
                    )
                    conn.commit()
                raw_summary["sources"][source] = {"ok": False, "endpoint": redact_endpoint(endpoint), "raw_path": str(raw_path), "error": error}
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if conn:
                    write_retrieval(
                        conn,
                        source=source,
                        query=args.query,
                        endpoint=redact_endpoint(endpoint),
                        status_code=None,
                        raw_path=None,
                        result_count=None,
                        error=error,
                    )
                    conn.commit()
                raw_summary["sources"][source] = {"ok": False, "endpoint": redact_endpoint(endpoint), "error": error}
            if source == "arxiv":
                time.sleep(3.2)
    finally:
        if conn:
            conn.close()
    print(json.dumps(raw_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
