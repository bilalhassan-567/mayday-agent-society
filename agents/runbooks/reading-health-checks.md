# Reading the /health checks

`/health` returns JSON with a `checks` object; each maps to a real dependency and
to the setting that governs it:

- `database` -> user store reachability (`user_store_path`)
- `connection_pool` -> free connections (`db_pool_available`)
- `routing` -> edit save-route resolves (`edit_save_route`)
- `orders_dependency` -> enrichment latency vs budget (`orders_service_delay_ms`)
- `object_storage` -> OSS credentials (`oss_api_key`)

The failing check name points almost directly at the corrupted setting. Always
cross-check with `config.read` and the log before proposing a fix. `/health` is
derived from live probes, never from any fault registry.
