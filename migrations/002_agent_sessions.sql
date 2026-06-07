CREATE TABLE IF NOT EXISTS agent_sessions (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  baton_id TEXT,
  role TEXT NOT NULL,
  adapter TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planned',
  control_mode TEXT NOT NULL DEFAULT 'none',
  control_ref TEXT NOT NULL DEFAULT '',
  packet_path TEXT NOT NULL DEFAULT '',
  command_json TEXT NOT NULL DEFAULT '[]',
  started_at TEXT,
  last_seen_at TEXT,
  ended_at TEXT,
  exit_code INTEGER,
  summary TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id),
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_run_status ON agent_sessions(run_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_baton ON agent_sessions(baton_id);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_seen ON agent_sessions(last_seen_at);
