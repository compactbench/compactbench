-- The owner's daily report. Totals only: no visitor, IP address or account is stored here.
CREATE TABLE daily_events (
  day TEXT NOT NULL,
  event TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, event)
);
CREATE TABLE daily_snapshots (
  day TEXT NOT NULL,
  key TEXT NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY (day, key)
);
CREATE TABLE milestones (
  key TEXT PRIMARY KEY,
  day TEXT NOT NULL
);
