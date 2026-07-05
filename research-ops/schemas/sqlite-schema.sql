PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS papers (
  id INTEGER PRIMARY KEY,
  canonical_id TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  year INTEGER,
  published_date TEXT,
  doi TEXT,
  arxiv_id TEXT,
  openalex_id TEXT,
  source TEXT,
  url TEXT,
  pdf_url TEXT,
  abstract TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS authors (
  paper_id INTEGER NOT NULL,
  position INTEGER NOT NULL,
  name TEXT NOT NULL,
  orcid TEXT,
  metadata_json TEXT,
  PRIMARY KEY (paper_id, position),
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS identifiers (
  paper_id INTEGER NOT NULL,
  id_type TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (paper_id, id_type, value),
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS retrievals (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  query TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  status_code INTEGER,
  raw_path TEXT,
  result_count INTEGER,
  error TEXT
);

CREATE TABLE IF NOT EXISTS zotero_links (
  paper_id INTEGER NOT NULL,
  library_type TEXT NOT NULL,
  library_id TEXT NOT NULL,
  item_key TEXT NOT NULL,
  collection_key TEXT,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (paper_id, library_type, library_id),
  FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_papers_openalex_id ON papers(openalex_id);
CREATE INDEX IF NOT EXISTS idx_papers_published_date ON papers(published_date);
CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name);
