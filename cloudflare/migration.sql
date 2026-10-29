-- Guardrail Manager (Cloudflare port), D1 schema. Apply with:
--   wrangler d1 migrations apply guardrail-manager --remote
-- The app's own data only: template default, scan cache, audit log,
-- login sessions. No secrets are stored here (ACCESS_CODE and
-- GITHUB_TOKEN are Worker secrets, never rows in this DB).

-- Key/value settings. Holds Jay's Template Default policy text
-- under key 'default_template'.
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Login sessions created by POST /api/login (same pattern as the
-- Gutter Genie quote app): the cookie holds the token, this table
-- is what makes a token valid.
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Scan cache: one summary row per repo...
CREATE TABLE IF NOT EXISTS scan_cache (
  repo TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'unscanned',
  error TEXT DEFAULT '',
  scanned_at REAL DEFAULT 0
);

-- ...and one row per guard artifact found in it, with the GitHub
-- blob sha the classification was made from.
CREATE TABLE IF NOT EXISTS scan_files (
  repo TEXT NOT NULL,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  label TEXT DEFAULT '',
  sha TEXT DEFAULT '',
  checked_at REAL DEFAULT 0,
  PRIMARY KEY (repo, path)
);
CREATE INDEX IF NOT EXISTS idx_scan_files_repo ON scan_files (repo);

-- Audit log of writes performed through the app (config layer only;
-- floor writes are refused before they ever reach GitHub, so they
-- never appear here as performed writes).
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  path TEXT DEFAULT '',
  action TEXT NOT NULL,
  commit_sha TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_log_id ON audit_log (id DESC);
