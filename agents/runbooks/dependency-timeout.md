# Internal dependency timeout

Symptom: `/orders` returns 504; the log shows `[/orders] internal dependency
failed` with "timed out". `/health` shows `orders_dependency` FAIL with
"latency <n>ms exceeds <budget>ms budget". `metrics.query` shows `/orders` as the
slowest page by far.

Cause: the orders-enrichment dependency latency (`orders_service_delay_ms`) was
raised above the timeout budget (`orders_service_timeout_ms`, 1500ms), so the call
never returns in time.

Fix: restore `orders_service_delay_ms` to a value well within the budget (40ms).
The DB and pool are healthy — do not misdiagnose this as a database problem.
