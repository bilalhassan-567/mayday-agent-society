# app_settings reference (healthy values)

The patient's real config. Healthy baselines:

| setting | healthy value | governs |
|---|---|---|
| `user_store_path` | `database/database.sqlite` | `/admin/users`, database check |
| `db_pool_available` | `10` | `/admin/users`, pool check |
| `edit_save_route` | `admin.users.update` | `/admin/users/{id}/edit`, routing check |
| `orders_service_delay_ms` | `40` | `/admin/orders`, dependency check |
| `orders_service_timeout_ms` | `1500` | orders timeout budget |
| `oss_api_key` | `LTAI-oss-valid-key-9f3a2` (any `LTAI…`, ≥12 chars) | `/admin/report`, storage check |

Read the current values with `config.read`; a value that deviates from this table
is the likely fault. Repair with `fix.apply(setting, healthy_value)`. Never edit
any other store to "fix" a symptom.
