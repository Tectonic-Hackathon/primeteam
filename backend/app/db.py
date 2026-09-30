import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector
from .config import DATABASE_URL, EMBED_DIM

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS people (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  team TEXT NOT NULL,
  country TEXT,
  seniority_years INT DEFAULT 0,
  email TEXT,
  active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  doc_type TEXT NOT NULL,          -- policy, procedure, manual, checklist, wiki, meeting, ticket, chat, email, analysis
  source_system TEXT NOT NULL,     -- SharePoint, Confluence, Teams, Outlook, Jira, Meeting Recorder, eBlox
  country TEXT,                    -- ISO-2 or NULL for global
  client TEXT,
  team TEXT,
  product TEXT,
  topics TEXT[] DEFAULT '{{}}',
  owner_id TEXT REFERENCES people(id),
  author_id TEXT REFERENCES people(id),
  created_at DATE NOT NULL,
  updated_at DATE NOT NULL,
  version TEXT,
  supersedes_id TEXT,
  location TEXT,                   -- human readable path / channel / meeting room
  url TEXT,
  body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id SERIAL PRIMARY KEY,
  document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
  section TEXT NOT NULL,
  line_start INT NOT NULL,
  line_end INT NOT NULL,
  text TEXT NOT NULL,
  topics TEXT[] DEFAULT '{{}}',
  embedding vector({EMBED_DIM}),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', section || ' ' || text)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);

CREATE TABLE IF NOT EXISTS edges (
  id SERIAL PRIMARY KEY,
  src TEXT NOT NULL,               -- e.g. person:els
  rel TEXT NOT NULL,               -- authored, edited, owns, answered, consulted, attended, assigned, mentions
  dst TEXT NOT NULL,               -- e.g. doc:POL-BE-001-v2, topic:notice_period
  at DATE NOT NULL,
  note TEXT
);
CREATE INDEX IF NOT EXISTS edges_src_idx ON edges (src);
CREATE INDEX IF NOT EXISTS edges_dst_idx ON edges (dst);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';  -- active, archived, retracted, needs_update

ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS date_known BOOLEAN NOT NULL DEFAULT TRUE;  -- FALSE: no date on the source at all
ALTER TABLE documents ADD COLUMN IF NOT EXISTS validated_at DATE;       -- owner confirmed "still valid" without editing
ALTER TABLE documents ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP;  -- last time a sync saw it in the source
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE TABLE IF NOT EXISTS document_versions (
  id SERIAL PRIMARY KEY,
  document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
  version_no INT NOT NULL,
  body TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  changed_by TEXT,
  changed_at DATE NOT NULL,
  change_summary TEXT,            -- e.g. "Entitlement: 30 days → 60 days"
  recorded_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS document_versions_doc_idx ON document_versions (document_id, version_no);

CREATE TABLE IF NOT EXISTS sync_runs (
  id SERIAL PRIMARY KEY,
  connector TEXT NOT NULL,
  mode TEXT NOT NULL,
  fetched INT DEFAULT 0,
  inserted INT DEFAULT 0,
  updated INT DEFAULT 0,
  unchanged INT DEFAULT 0,
  archived INT DEFAULT 0,
  since DATE,
  trigger TEXT DEFAULT 'manual',  -- manual, schedule, webhook
  started_at TIMESTAMP DEFAULT now(),
  finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
  id SERIAL PRIMARY KEY,
  kind TEXT NOT NULL,              -- request_update, confirm_valid, reassign_owner
  document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
  assignee_id TEXT REFERENCES people(id),
  requested_by TEXT,
  question TEXT,
  note TEXT,
  created_at TIMESTAMP DEFAULT now(),
  done BOOLEAN DEFAULT FALSE
);
"""


def connect():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def init_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
