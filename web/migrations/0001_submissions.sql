-- Ranked submissions made on the website. Bundles (code and sealed keys) live in R2;
-- this table holds status and what the rate limits count.
CREATE TABLE submissions (
  id TEXT PRIMARY KEY,
  github_id INTEGER NOT NULL,
  handle TEXT NOT NULL,
  method_name TEXT NOT NULL,
  method_version TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  model_label TEXT,
  status TEXT NOT NULL,
  message TEXT,
  score REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX submissions_by_user ON submissions (github_id, created_at);
CREATE INDEX submissions_by_time ON submissions (created_at);
