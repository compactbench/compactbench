-- Contact form rate limits: a keyed hash of the sender's IP address and the time, deleted
-- after a day. Messages themselves are emailed to the maintainer and never stored.
CREATE TABLE contact_log (
  ip_hash TEXT NOT NULL,
  at TEXT NOT NULL
);
CREATE INDEX contact_log_by_sender ON contact_log (ip_hash, at);
CREATE INDEX contact_log_by_time ON contact_log (at);
