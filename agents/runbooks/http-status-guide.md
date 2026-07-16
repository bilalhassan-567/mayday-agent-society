# HTTP status guide for this system

- **500 Internal Server Error** — the request reached the app but an operation
  threw. Seen on `/edit` (route not found) and `/report` (upload auth failure).
- **503 Service Unavailable** — a dependency the request needs is down or
  saturated. Seen on `/users` (dead store OR pool exhausted) and on `/health`
  whenever any check fails.
- **504 Gateway Timeout** — an internal/upstream call did not return in time.
  Seen on `/orders` (dependency timeout).

The status code narrows the fault class; the log signature and the failing
`/health` check pin the exact cause. A 504 is a latency problem, not availability.
