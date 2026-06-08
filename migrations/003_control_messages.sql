CREATE TABLE IF NOT EXISTS control_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  baton_id TEXT,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL DEFAULT '',
  target_label TEXT NOT NULL DEFAULT '',
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  delivery TEXT NOT NULL DEFAULT 'recorded_only',
  control_mode TEXT NOT NULL DEFAULT 'event',
  control_ref TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  claimed_at TEXT,
  claimed_by TEXT NOT NULL DEFAULT '',
  handled_at TEXT,
  summary TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (run_id) REFERENCES factory_runs(id),
  FOREIGN KEY (baton_id) REFERENCES batons(id)
);

CREATE INDEX IF NOT EXISTS idx_control_messages_run_status ON control_messages(run_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_control_messages_target_status ON control_messages(run_id, target_type, target_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_control_messages_baton ON control_messages(baton_id, status, created_at);
