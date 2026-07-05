from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lookup_papers as lookup  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = ROOT / "research-ops" / "library"
DB_PATH = LIBRARY_ROOT / "db" / "papers.sqlite"
PDF_ROOT = LIBRARY_ROOT / "pdf"
PROFILE_PATH = ROOT / "research-ops" / "config" / "search_profiles.json"
ZOTERO_BASE = "http://127.0.0.1:23119"
CONNECTOR_API_VERSION = "3"


class ZoteroLocalError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.I)
    return value or None


def looks_like_doi(value: str | None) -> bool:
    doi = normalize_doi(value)
    return bool(doi and re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.I))


def safe_header_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def load_library_config() -> dict[str, Any]:
    path = ROOT / "research-ops" / "config" / "library.json"
    return json.loads(path.read_text(encoding="utf-8"))


def default_zotero_target() -> str | None:
    config = load_library_config()
    return (
        (config.get("zotero_local_targets") or {})
        .get("candidate_collection", {})
        .get("target_id")
    )


def request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, Any, dict[str, str]]:
    url = ZOTERO_BASE + path
    data = None
    headers = {"X-Zotero-Connector-API-Version": CONNECTOR_API_VERSION}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            parsed: Any = None
            if body:
                if "application/json" in content_type:
                    parsed = json.loads(body.decode("utf-8"))
                else:
                    parsed = body.decode("utf-8", errors="replace")
            return int(response.status), parsed, dict(response.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ZoteroLocalError(f"{method} {path} failed: HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ZoteroLocalError(
            "Zotero local Connector is not reachable. Open Zotero Desktop and keep local API enabled."
        ) from exc


def post_binary(path: str, *, body: bytes, content_type: str, headers: dict[str, str]) -> int:
    merged_headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "X-Zotero-Connector-API-Version": CONNECTOR_API_VERSION,
        **headers,
    }
    request = urllib.request.Request(
        ZOTERO_BASE + path,
        data=body,
        headers=merged_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
            return int(response.status)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise ZoteroLocalError(f"POST {path} failed: HTTP {exc.code}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise ZoteroLocalError(f"POST {path} failed: {exc}") from exc


def get_selected_target() -> dict[str, Any]:
    _, selected, _ = request_json("/connector/getSelectedCollection", method="POST", payload={})
    if not isinstance(selected, dict):
        raise ZoteroLocalError("Unexpected Zotero selected-collection response.")
    collection_id = selected.get("id")
    selected["selectedTargetID"] = f"C{collection_id}" if collection_id else f"L{selected.get('libraryID')}"
    return selected


def resolve_target(selected: dict[str, Any], target: str | None, target_name: str | None) -> dict[str, Any]:
    targets = selected.get("targets") or []
    if target:
        for item in targets:
            if item.get("id") == target:
                return item
        raise ZoteroLocalError(f"Target {target!r} is not available in Zotero.")
    if target_name:
        matches = [item for item in targets if item.get("name") == target_name]
        if len(matches) != 1:
            names = ", ".join(f"{item.get('id')}:{item.get('name')}" for item in targets)
            raise ZoteroLocalError(
                f"Target name {target_name!r} matched {len(matches)} targets. Available targets: {names}"
            )
        return matches[0]
    selected_id = selected.get("selectedTargetID")
    for item in targets:
        if item.get("id") == selected_id:
            return item
    return {
        "id": selected_id,
        "name": selected.get("name") or selected.get("libraryName") or "Selected Zotero target",
        "filesEditable": selected.get("filesEditable"),
        "level": 0,
    }


def record_to_connector_item(record: dict[str, Any], connector_id: str, tags: list[str]) -> dict[str, Any]:
    doi = normalize_doi(record.get("doi"))
    arxiv_id = record.get("arxiv_id")
    item_type = "preprint" if arxiv_id else "journalArticle"
    item: dict[str, Any] = {
        "id": connector_id,
        "itemType": item_type,
        "title": record.get("title") or "Untitled",
        "creators": [],
        "abstractNote": record.get("abstract") or "",
        "date": record.get("published_date") or str(record.get("year") or ""),
        "url": record.get("url") or "",
        "libraryCatalog": "arXiv" if arxiv_id else "OpenAlex",
        "tags": [{"tag": tag} for tag in tags],
        "notes": [],
    }
    if doi:
        item["DOI"] = doi
    if arxiv_id:
        item["archive"] = "arXiv"
        item["archiveID"] = f"arXiv:{arxiv_id}"
        item["extra"] = f"arXiv: {arxiv_id}"
    elif record.get("source"):
        item["publicationTitle"] = record.get("source")
    if record.get("openalex_id"):
        extra = item.get("extra", "")
        item["extra"] = (extra + "\n" if extra else "") + f"OpenAlex: {record['openalex_id']}"
    if record.get("_ccf_profile"):
        extra = item.get("extra", "")
        ccf_line = f"CCF Profile: {record.get('_ccf_profile')} {record.get('_ccf_rank')}-{record.get('_ccf_venue')}"
        item["extra"] = (extra + "\n" if extra else "") + ccf_line

    for author in record.get("authors") or []:
        name = (author.get("name") or "").strip()
        if not name:
            continue
        parts = name.split()
        if len(parts) == 1:
            item["creators"].append({"creatorType": "author", "firstName": "", "lastName": parts[0]})
        else:
            item["creators"].append(
                {"creatorType": "author", "firstName": " ".join(parts[:-1]), "lastName": parts[-1]}
            )
    return item


def load_search_profile(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    profiles = json.loads(PROFILE_PATH.read_text(encoding="utf-8")).get("profiles", {})
    profile = profiles.get(name)
    if not profile:
        available = ", ".join(sorted(profiles))
        raise ZoteroLocalError(f"Unknown search profile {name!r}. Available profiles: {available}")
    profile["_name"] = name
    return profile


def openalex_profile_url(query: str, per_page: int, since: str, until: str | None) -> str:
    filters = [f"from_publication_date:{since}"]
    if until:
        filters.append(f"to_publication_date:{until}")
    params = {
        "search": query,
        "filter": ",".join(filters),
        "sort": "relevance_score:desc",
        "per_page": str(per_page),
        "select": "id,doi,title,publication_year,publication_date,type,cited_by_count,authorships,open_access,primary_location,locations",
    }
    api_key = os.environ.get("OPENALEX_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return "https://api.openalex.org/works?" + urllib.parse.urlencode(params)


def openalex_doi_url(doi: str) -> str:
    params = {}
    api_key = os.environ.get("OPENALEX_API_KEY")
    if api_key:
        params["api_key"] = api_key
    suffix = urllib.parse.urlencode(params)
    url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="")
    return f"{url}?{suffix}" if suffix else url


def expand_profile_queries(query: str, profile: dict[str, Any]) -> list[str]:
    normalized = normalize_text(query)
    queries = [query]
    expansions = profile.get("query_expansions") or {}
    if any(term in normalized for term in ["re-identification", "reid", "re-id"]):
        queries.extend(expansions.get("reid", []))
    if any(term in normalized for term in ["visible infrared", "visible-infrared", "rgb-infrared", "vi-reid"]):
        base_reid = "person re-identification"
        queries.extend(f"{term} {base_reid}" for term in expansions.get("visible-infrared", []))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in queries:
        key = normalize_text(item)
        if key and key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped[:8]


def source_names(record: dict[str, Any]) -> list[str]:
    names = []
    if record.get("source"):
        names.append(str(record["source"]))
    metadata = record.get("metadata") or {}
    for location in [metadata.get("primary_location"), *(metadata.get("locations") or [])]:
        if not isinstance(location, dict):
            continue
        source = location.get("source") or {}
        display_name = source.get("display_name")
        if display_name:
            names.append(display_name)
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize_text(name)
        if key and key not in seen:
            deduped.append(name)
            seen.add(key)
    return deduped


def match_profile_venue(
    record: dict[str, Any], profile: dict[str, Any], rank: str, venue_group: str
) -> dict[str, str] | None:
    allowed = {"A", "B"} if rank == "AB" else {rank}
    groups = profile.get("venue_groups") or {}
    allowed_group = set(groups.get(venue_group) or groups.get("all") or [])
    venues = [
        venue
        for venue in profile.get("venues", [])
        if venue.get("rank") in allowed and (not allowed_group or venue.get("abbr") in allowed_group)
    ]
    source_haystack = " | ".join(source_names(record))
    normalized_source = normalize_text(source_haystack)
    for venue in venues:
        aliases = [venue.get("abbr", ""), *(venue.get("aliases") or [])]
        for alias in aliases:
            alias_key = normalize_text(alias)
            if alias_key and alias_key in normalized_source:
                return {
                    "profile": profile["_name"],
                    "venue_group": venue_group,
                    "venue": venue.get("abbr") or alias,
                    "rank": venue.get("rank") or "",
                    "matched_source": source_haystack,
                }
    return None


def profile_record_score(record: dict[str, Any]) -> tuple[int, int, int]:
    rank_score = 2 if record.get("_ccf_rank") == "A" else 1
    year_score = int(record.get("year") or 0)
    cited_score = int(((record.get("metadata") or {}).get("cited_by_count") or 0))
    return (rank_score, year_score, cited_score)


def lookup_openalex_profile_records(args: argparse.Namespace, profile: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_dir = LIBRARY_ROOT / "raw" / "openalex"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for expanded_query in expand_profile_queries(args.query, profile):
        endpoint = openalex_profile_url(expanded_query, args.candidate_limit, args.since, args.until)
        status, raw = lookup.fetch(endpoint, accept="application/json")
        raw_path = raw_dir / (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{lookup.slugify(args.profile or 'profile')}-{lookup.slugify(expanded_query)}.json"
        )
        raw_path.write_bytes(raw)
        if status < 200 or status >= 300:
            preview = raw[:200].decode("utf-8", errors="replace").strip()
            raise ZoteroLocalError(
                f"openalex returned HTTP {status}. Raw response saved to {raw_path}. Preview: {preview}"
            )
        payload = json.loads(raw.decode("utf-8"))
        result_count = (payload.get("meta") or {}).get("count")
        for record in lookup.parse_openalex(payload):
            match = match_profile_venue(record, profile, args.ccf_rank, args.venue_group)
            if not match:
                continue
            key = record.get("openalex_id") or record.get("doi") or normalize_text(record.get("title"))
            if key in seen:
                continue
            seen.add(str(key))
            record["_lookup_source"] = "openalex"
            record["_lookup_endpoint"] = lookup.redact_endpoint(endpoint)
            record["_lookup_status"] = status
            record["_lookup_result_count"] = result_count
            record["_lookup_raw_path"] = str(raw_path)
            record["_profile_query"] = expanded_query
            record["_ccf_profile"] = match["profile"]
            record["_ccf_venue_group"] = match["venue_group"]
            record["_ccf_venue"] = match["venue"]
            record["_ccf_rank"] = match["rank"]
            record["_ccf_matched_source"] = match["matched_source"]
            records.append(record)
    records.sort(key=profile_record_score, reverse=True)
    return records[: args.limit]


def lookup_openalex_doi_records(
    args: argparse.Namespace,
    *,
    doi: str,
    profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    raw_dir = LIBRARY_ROOT / "raw" / "openalex"
    raw_dir.mkdir(parents=True, exist_ok=True)
    endpoint = openalex_doi_url(doi)
    status, raw = lookup.fetch(endpoint, accept="application/json")
    raw_path = raw_dir / (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-doi-{lookup.slugify(doi)}.json"
    )
    raw_path.write_bytes(raw)
    if status < 200 or status >= 300:
        preview = raw[:200].decode("utf-8", errors="replace").strip()
        raise ZoteroLocalError(
            f"openalex DOI lookup returned HTTP {status}. Raw response saved to {raw_path}. Preview: {preview}"
        )
    payload = json.loads(raw.decode("utf-8"))
    records = lookup.parse_openalex({"results": [payload]})
    for record in records:
        record["_lookup_source"] = "openalex"
        record["_lookup_endpoint"] = lookup.redact_endpoint(endpoint)
        record["_lookup_status"] = status
        record["_lookup_result_count"] = 1
        record["_lookup_raw_path"] = str(raw_path)
        if profile:
            match = match_profile_venue(record, profile, args.ccf_rank, args.venue_group)
            if not match:
                return []
            record["_profile_query"] = doi
            record["_ccf_profile"] = match["profile"]
            record["_ccf_venue_group"] = match["venue_group"]
            record["_ccf_venue"] = match["venue"]
            record["_ccf_rank"] = match["rank"]
            record["_ccf_matched_source"] = match["matched_source"]
    return records[: args.limit]


def lookup_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    profile = load_search_profile(args.profile)
    doi = normalize_doi(args.doi) if args.doi else normalize_doi(args.query) if looks_like_doi(args.query) else None
    if doi:
        if args.source not in {"openalex", "all"}:
            raise ZoteroLocalError("DOI lookup currently uses OpenAlex; set --source openalex or --source all.")
        return lookup_openalex_doi_records(args, doi=doi, profile=profile)
    if profile:
        if args.source not in {"openalex", "all"}:
            raise ZoteroLocalError("Search profiles currently use OpenAlex; set --source openalex or --source all.")
        return lookup_openalex_profile_records(args, profile)
    sources = ["arxiv", "openalex"] if args.source == "all" else [args.source]
    records: list[dict[str, Any]] = []
    for source in sources:
        if source == "openalex":
            endpoint = lookup.openalex_url(args.query, args.limit, args.since, args.until, args.title_only)
            raw_ext = "json"
            status, raw = lookup.fetch(endpoint, accept="application/json")
        else:
            endpoint = lookup.arxiv_url(args.query, args.limit)
            raw_ext = "xml"
            status, raw = lookup.fetch(endpoint, accept="*/*")
        raw_dir = LIBRARY_ROOT / "raw" / source
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{lookup.slugify(args.query)}.{raw_ext}"
        raw_path.write_bytes(raw)
        if status < 200 or status >= 300:
            preview = raw[:200].decode("utf-8", errors="replace").strip()
            raise ZoteroLocalError(
                f"{source} returned HTTP {status}. Raw response saved to {raw_path}. Preview: {preview}"
            )
        if source == "openalex":
            payload = json.loads(raw.decode("utf-8"))
            source_records = lookup.parse_openalex(payload)
            result_count = (payload.get("meta") or {}).get("count")
        else:
            result_count, source_records = lookup.parse_arxiv(raw)
        for record in source_records:
            record["_lookup_source"] = source
            record["_lookup_endpoint"] = lookup.redact_endpoint(endpoint)
            record["_lookup_status"] = status
            record["_lookup_result_count"] = result_count
            record["_lookup_raw_path"] = str(raw_path)
        records.extend(source_records)
        if source == "arxiv":
            time.sleep(3.2)
    return records if args.source == "all" else records[: args.limit]


def write_records_to_db(records: list[dict[str, Any]], db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            grouped.setdefault(record.get("_lookup_source") or "unknown", []).append(record)
        for source, source_records in grouped.items():
            first = source_records[0]
            lookup.write_retrieval(
                conn,
                source=source,
                query=first.get("_lookup_query") or "",
                endpoint=first.get("_lookup_endpoint") or "",
                status_code=first.get("_lookup_status"),
                raw_path=Path(first["_lookup_raw_path"]) if first.get("_lookup_raw_path") else None,
                result_count=first.get("_lookup_result_count"),
                error=None,
            )
        count = lookup.upsert_records(conn, records)
        conn.commit()
        return {"papers_written": count}
    finally:
        conn.close()


def paper_id_for_record(conn: sqlite3.Connection, record: dict[str, Any]) -> int | None:
    row = conn.execute(
        "SELECT id FROM papers WHERE canonical_id = ?",
        (record.get("canonical_id"),),
    ).fetchone()
    return int(row[0]) if row else None


def write_zotero_link(
    db_path: Path,
    record: dict[str, Any],
    *,
    item_key: str,
    target_id: str | None,
    library_id: str = "0",
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        paper_id = paper_id_for_record(conn, record)
        if paper_id is None:
            lookup.upsert_records(conn, [record])
            paper_id = paper_id_for_record(conn, record)
        if paper_id is None:
            raise RuntimeError("Could not resolve paper_id after upsert.")
        conn.execute(
            """
            INSERT INTO zotero_links(paper_id, library_type, library_id, item_key, collection_key, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id, library_type, library_id) DO UPDATE SET
              item_key=excluded.item_key,
              collection_key=excluded.collection_key,
              synced_at=excluded.synced_at
            """,
            (paper_id, "user", library_id, item_key, target_id, utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def download_pdf(record: dict[str, Any], output_root: Path) -> dict[str, Any]:
    pdf_url = record.get("pdf_url")
    if not pdf_url:
        return {"ok": False, "reason": "No PDF URL was available."}
    if pdf_url.startswith("http://arxiv.org/"):
        pdf_url = "https://arxiv.org/" + pdf_url[len("http://arxiv.org/") :]
    status, raw = lookup.fetch(pdf_url, accept="application/pdf", timeout=120)
    if status < 200 or status >= 300:
        return {"ok": False, "reason": f"PDF download returned HTTP {status}.", "url": pdf_url}
    if b"%PDF" not in raw[:1024]:
        return {"ok": False, "reason": "Downloaded content did not look like a PDF.", "url": pdf_url}
    source = record.get("_lookup_source") or ("arxiv" if record.get("arxiv_id") else "openalex")
    source_dir = output_root / source
    source_dir.mkdir(parents=True, exist_ok=True)
    base = record.get("arxiv_id") or normalize_doi(record.get("doi")) or record.get("canonical_id") or record["title"]
    filename = f"{lookup.slugify(str(base))}-{lookup.slugify(record['title'])[:48]}.pdf"
    path = source_dir / filename
    path.write_bytes(raw)
    return {"ok": True, "path": str(path), "url": pdf_url, "bytes": len(raw)}


def zotero_query_items(query: str, *, limit: int = 25) -> list[dict[str, Any]]:
    quoted = urllib.parse.urlencode({"q": query, "qmode": "everything", "limit": str(limit)})
    _, data, _ = request_json(f"/api/users/0/items/top?{quoted}")
    return data if isinstance(data, list) else []


def find_zotero_item(record: dict[str, Any]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for value in [normalize_doi(record.get("doi")), record.get("arxiv_id"), record.get("title")]:
        if value:
            candidates.extend(zotero_query_items(str(value), limit=25))
    title = normalize_text(record.get("title"))
    doi = normalize_doi(record.get("doi"))
    arxiv_id = record.get("arxiv_id")
    for candidate in candidates:
        data = candidate.get("data") or {}
        candidate_doi = normalize_doi(data.get("DOI"))
        candidate_title = normalize_text(data.get("title"))
        extra = data.get("extra") or ""
        archive_id = data.get("archiveID") or ""
        if doi and candidate_doi == doi:
            return candidate
        if arxiv_id and (arxiv_id in extra or arxiv_id in archive_id or arxiv_id in (data.get("url") or "")):
            return candidate
        if title and candidate_title == title:
            return candidate
    return None


def recent_matching_item(record: dict[str, Any]) -> dict[str, Any] | None:
    _, data, _ = request_json("/api/users/0/items/top?sort=dateModified&direction=desc&limit=30")
    items = data if isinstance(data, list) else []
    title = normalize_text(record.get("title"))
    for item in items:
        if normalize_text((item.get("data") or {}).get("title")) == title:
            return item
    return None


def find_pdf_attachment(item_key: str) -> dict[str, Any] | None:
    _, data, _ = request_json(f"/api/users/0/items/{item_key}/children")
    children = data if isinstance(data, list) else []
    for child in children:
        child_data = child.get("data") or {}
        if child_data.get("itemType") == "attachment" and child_data.get("contentType") == "application/pdf":
            return child
    return None


def save_item_to_zotero(
    record: dict[str, Any],
    *,
    target_id: str | None,
    tags: list[str],
    pdf_result: dict[str, Any] | None,
) -> dict[str, Any]:
    session_id = f"codex-{uuid.uuid4().hex}"
    connector_item_id = record.get("canonical_id") or f"codex-{uuid.uuid4().hex}"
    item = record_to_connector_item(record, connector_item_id, tags)
    payload = {
        "sessionID": session_id,
        "uri": record.get("url") or record.get("pdf_url") or "",
        "items": [item],
    }
    status, _, _ = request_json("/connector/saveItems", method="POST", payload=payload, timeout=60)
    if status != 201:
        raise ZoteroLocalError(f"/connector/saveItems returned unexpected status {status}.")
    if target_id:
        request_json(
            "/connector/updateSession",
            method="POST",
            payload={"sessionID": session_id, "target": target_id, "tags": tags, "note": ""},
            timeout=60,
        )
    if pdf_result and pdf_result.get("ok"):
        pdf_path = Path(str(pdf_result["path"]))
        metadata = {
            "sessionID": session_id,
            "parentItemID": connector_item_id,
            "title": "Full Text PDF",
            "url": pdf_result.get("url") or record.get("pdf_url") or "",
        }
        post_binary(
            f"/connector/saveAttachment?{urllib.parse.urlencode({'sessionID': session_id})}",
            body=pdf_path.read_bytes(),
            content_type="application/pdf",
            headers={"X-Metadata": safe_header_json(metadata)},
        )
    item_info = recent_matching_item(record) or find_zotero_item(record)
    if not item_info:
        raise ZoteroLocalError("Item was saved but could not be found through Zotero local API.")
    attachment = find_pdf_attachment(item_info["key"])
    return {
        "session_id": session_id,
        "item_key": item_info["key"],
        "attachment_key": attachment.get("key") if attachment else None,
    }


def open_zotero_item(item_key: str, attachment_key: str | None) -> str:
    uri = (
        f"zotero://open-pdf/library/items/{attachment_key}"
        if attachment_key
        else f"zotero://select/library/items/{item_key}"
    )
    if os.name == "nt":
        os.startfile(uri)  # type: ignore[attr-defined]
    else:
        raise ZoteroLocalError("Opening Zotero URL schemes is currently implemented for Windows only.")
    return uri


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search papers, download PDFs, import into local Zotero Desktop, and optionally open them."
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--doi", help="Fetch one OpenAlex work by DOI before importing.")
    parser.add_argument("--source", choices=["arxiv", "openalex", "all"], default="arxiv")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--since", default="2025-01-01")
    parser.add_argument("--until")
    parser.add_argument("--title-only", action="store_true")
    parser.add_argument("--profile", choices=["ccf-ai-ab"], help="Use a local venue-aware search profile.")
    parser.add_argument("--ccf-rank", choices=["A", "B", "AB"], default="AB")
    parser.add_argument(
        "--venue-group",
        choices=["all", "vision", "ml", "nlp", "general-ai", "robotics"],
        default="all",
        help="Restrict the profile to a venue group.",
    )
    parser.add_argument("--candidate-limit", type=int, default=100, help="OpenAlex candidates to fetch before local profile filtering.")
    parser.add_argument("--target", help="Zotero Connector tree target, e.g. L1 or C25. Defaults to the candidate collection from library.json.")
    parser.add_argument("--target-name", help="Exact Zotero target collection name.")
    parser.add_argument("--tag", action="append", default=[], help="Tag to add to newly imported Zotero items.")
    parser.add_argument("--download-pdf", action="store_true", help="Download PDFs during dry-run too.")
    parser.add_argument("--skip-pdf", action="store_true", help="Do not download or attach PDFs.")
    parser.add_argument("--yes", action="store_true", help="Actually write new items into the local Zotero library.")
    parser.add_argument("--open", action="store_true", help="Open the imported or existing Zotero item/PDF.")
    parser.add_argument("--force-duplicate", action="store_true", help="Create a Zotero item even if a match exists.")
    parser.add_argument("--no-db", action="store_true", help="Do not update research-ops SQLite metadata/link tables.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--pdf-root", default=str(PDF_ROOT))
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        db_path = Path(args.db).expanduser().resolve()
        pdf_root = Path(args.pdf_root).expanduser().resolve()
        selected = get_selected_target()
        target_id = args.target or (None if args.target_name else default_zotero_target())
        target = resolve_target(selected, target_id, args.target_name)
        records = lookup_records(args)
        for record in records:
            record["_lookup_query"] = args.query
        if not args.no_db and records:
            write_records_to_db(records, db_path)

        summary: dict[str, Any] = {
            "dry_run": not args.yes,
            "zotero_target": {
                "id": target.get("id"),
                "name": target.get("name"),
                "current_selected": selected.get("selectedTargetID"),
                "files_editable": target.get("filesEditable"),
            },
            "records": [],
        }
        if not records:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 2

        for record in records:
            item_summary: dict[str, Any] = {
                "title": record.get("title"),
                "source": record.get("_lookup_source"),
                "doi": normalize_doi(record.get("doi")),
                "arxiv_id": record.get("arxiv_id"),
                "pdf_url": record.get("pdf_url"),
                "ccf_profile": record.get("_ccf_profile"),
                "ccf_venue_group": record.get("_ccf_venue_group"),
                "ccf_rank": record.get("_ccf_rank"),
                "ccf_venue": record.get("_ccf_venue"),
                "ccf_matched_source": record.get("_ccf_matched_source"),
                "profile_query": record.get("_profile_query"),
            }
            existing = None if args.force_duplicate else find_zotero_item(record)
            if existing:
                attachment = find_pdf_attachment(existing["key"])
                item_summary["zotero"] = {
                    "status": "existing",
                    "item_key": existing["key"],
                    "attachment_key": attachment.get("key") if attachment else None,
                }
                if args.open:
                    item_summary["opened"] = open_zotero_item(
                        existing["key"], attachment.get("key") if attachment else None
                    )
                summary["records"].append(item_summary)
                continue

            pdf_result = None
            should_download = bool(record.get("pdf_url")) and not args.skip_pdf and (args.yes or args.download_pdf)
            if should_download:
                pdf_result = download_pdf(record, pdf_root)
                item_summary["pdf_download"] = pdf_result
            elif not record.get("pdf_url"):
                item_summary["pdf_download"] = {"ok": False, "reason": "No PDF URL was available."}
            else:
                item_summary["pdf_download"] = {"ok": False, "reason": "PDF download skipped in dry-run."}

            if args.yes:
                imported = save_item_to_zotero(
                    record,
                    target_id=target.get("id"),
                    tags=args.tag,
                    pdf_result=pdf_result,
                )
                item_summary["zotero"] = {"status": "imported", **imported}
                if not args.no_db:
                    write_zotero_link(
                        db_path,
                        record,
                        item_key=imported["item_key"],
                        target_id=target.get("id"),
                        library_id=str(selected.get("libraryID") or 0),
                    )
                if args.open:
                    item_summary["opened"] = open_zotero_item(imported["item_key"], imported.get("attachment_key"))
            else:
                item_summary["zotero"] = {"status": "dry-run", "would_import": True}
            summary["records"].append(item_summary)

        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
