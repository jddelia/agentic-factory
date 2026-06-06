PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factory_runs (
  id TEXT PRIMARY KEY,
  project_root TEXT NOT NULL,
  objective TEXT NOT NULL DEFAULT '',
  work_mode TEXT NOT NULL DEFAULT 'balanced',
  topology TEXT NOT NULL DEFAULT 'executive_as_ledger',
  status TEXT NOT NULL DEFAULT 'active',
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  paused_at TEXT,
  resumed_at TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS actors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  role TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  thread_id TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  reasoning TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id)
);

CREATE TABLE IF NOT EXISTS batons (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  title TEXT NOT NULL,
  owner TEXT NOT NULL DEFAULT '',
  owner_thread TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'assigned',
  scope TEXT NOT NULL DEFAULT '',
  acceptance_tier TEXT NOT NULL DEFAULT 'integration',
  verification_level TEXT NOT NULL DEFAULT 'focused',
  model TEXT NOT NULL DEFAULT '',
  reasoning TEXT NOT NULL DEFAULT '',
  assigned_at TEXT NOT NULL,
  handed_off_at TEXT,
  accepted_at TEXT,
  blocked_at TEXT,
  commit_sha TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id)
);

CREATE TABLE IF NOT EXISTS handoffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  baton_id TEXT NOT NULL,
  files_changed_json TEXT NOT NULL DEFAULT '[]',
  behavior_changed TEXT NOT NULL DEFAULT '',
  commands_run_json TEXT NOT NULL DEFAULT '[]',
  verification_json TEXT NOT NULL DEFAULT '[]',
  risks TEXT NOT NULL DEFAULT '',
  next_recommended TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  baton_id TEXT NOT NULL,
  reviewer TEXT NOT NULL DEFAULT '',
  reviewer_thread TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'recorded',
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE TABLE IF NOT EXISTS review_findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_id INTEGER NOT NULL,
  severity TEXT NOT NULL DEFAULT '',
  file TEXT NOT NULL DEFAULT '',
  line INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  summary TEXT NOT NULL DEFAULT '',
  resolution TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (review_id) REFERENCES reviews(id)
);

CREATE TABLE IF NOT EXISTS verification_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  baton_id TEXT,
  command TEXT NOT NULL,
  package_name TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL,
  duration_ms INTEGER,
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE TABLE IF NOT EXISTS commits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  baton_id TEXT,
  sha TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  pushed_status TEXT NOT NULL DEFAULT 'unknown',
  created_at TEXT NOT NULL,
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE TABLE IF NOT EXISTS blockers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  baton_id TEXT,
  blocker_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  owner TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  resolved_by TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id),
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE TABLE IF NOT EXISTS locks (
  name TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  baton_id TEXT,
  holder TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'held',
  acquired_at TEXT NOT NULL,
  released_at TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id),
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  run_id TEXT,
  baton_id TEXT,
  summary TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id),
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE INDEX IF NOT EXISTS idx_events_run_time ON events(run_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_baton_time ON events(baton_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_batons_run_status ON batons(run_id, status);
CREATE INDEX IF NOT EXISTS idx_verification_baton ON verification_runs(baton_id);
CREATE INDEX IF NOT EXISTS idx_reviews_baton ON reviews(baton_id);

