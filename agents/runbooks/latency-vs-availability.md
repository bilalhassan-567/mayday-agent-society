# Latency vs availability (decoy alert)

A slow dependency can masquerade as a database problem: both "feel like" a backend
stall and both can cascade into a sick `/health`. Separate them:

- A **timeout** (`dependency_timeout`) shows a 504 on `/orders` and, in
  `metrics.query`, a very high `latency_ms` on `/orders` specifically — while
  `database` and `connection_pool` checks stay GREEN.
- A **database** fault shows a 503 on `/users` and fails fast (low latency); the
  `database`/`connection_pool` checks are RED.

If the DB checks are green and only orders is slow, it is latency, not
availability. Cite the metric and the healthy DB checks in the debate.
