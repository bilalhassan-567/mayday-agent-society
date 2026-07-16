# Connection pool exhaustion

Symptom: `/users` returns 503; the log shows `[/users] connection pool exhausted`
and `/health` reports `connection_pool` FAIL with "0/10 available". Crucially the
user store host is REACHABLE — the request is refused before it ever queries.

Cause: `db_pool_available` has dropped to 0 (leaked/held connections). This is
NOT a dead host: `db.inspect` on `users` still works, and the database health
check may still pass.

Fix: restore `db_pool_available` to the pool size (10). Distinguish from a dead
host by checking whether the store is reachable (it is, for pool exhaustion).
