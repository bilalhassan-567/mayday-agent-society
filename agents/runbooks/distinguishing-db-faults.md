# Distinguishing the two /users 503s (decoy alert)

Both `db_host_broken` and `db_pool_exhausted` present as a 503 on `/users` plus a
sick `/health`. They are easy to confuse — verify before you commit.

Discriminating evidence:
- Read the log (`log.search "users"`): "failed to read user store" => host/target
  problem; "connection pool exhausted" => pool problem.
- `config.read`: is `user_store_path` a sane location, or `db_pool_available` = 0?
- `db.inspect users`: if it returns rows, the store is reachable => pool problem,
  not a dead host.

Do not let the shared 503 symptom collapse both hypotheses into one — cite the
log signature and the config value that actually differs.
