# Database connection refused / dead host

Symptom: `/admin/users` returns 503 and the log shows `[/admin/users] failed to
read user store` with a connection or "unable to open database" error. `/health`
shows the `database` check FAIL with "user store unreachable".

Cause: the user store connection target (`user_store_path`) points at a host or
path that does not exist — e.g. a decommissioned DB primary. Every connection
attempt is refused; the pool itself is fine.

Fix: restore `user_store_path` to the live user store — the application database
at `database/database.sqlite` (the dev SQLite store, relative to the app root; a
DB host in prod). Then confirm the `database` health check goes green and
`/admin/users` returns 200.
