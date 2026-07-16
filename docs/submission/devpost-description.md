# Mayday — Devpost Submission Text

Paste-ready for the Devpost project page. Track 3: Agent Society. Trim to fit any field
limits; the **Elevator pitch** and **What it does** are the must-keeps.

---

## Elevator pitch (one line)
A society of AI agents that watch a live web app, and when it breaks, **bid** for the
case, **debate** the root cause with staked confidence, **verify** a fix against real
health checks, and **settle trust** so the society measurably improves — 3× more reliable
than a single agent on the same model.

---

## Inspiration
This project's real origin goes back to my final-year degree project, 2023–2024. A senior
alumnus working at IBM pointed me and my partner toward a problem IBM's own Watsonx team
was exploring at the time: could an LLM watch a database's error logs and fix things
automatically? We built a rough version of that idea — a local, Linux-based Python script.
A Watchman-style process tailed the database's log file, and the moment an error appeared,
it shipped the log straight to Gemini, parsed whatever fix came back, and applied it
directly in the terminal. No debate, no second opinion, no check that the fix actually
worked — just one model's guess, applied on faith.

It worked often enough to be exciting. Of five DBAs on the system, only two actually used
it to monitor and act on issues day to day — and whenever the same problem kept recurring,
a DBA still had to step in and fix it manually.

At the time — 2023, before "agent," "RAG," or "MCP" were words I knew — I didn't have the
vocabulary for what was actually missing: verification, disagreement, and trust. Mayday is
what that same idea looks like now that I do. Instead of one model guessing and hoping, a
society of agents debates with staked confidence, and nothing is ever trusted until a real
health check proves the fix worked. The naive version from my degree taught me exactly what
to build next.

On-call incident response is where a single AI agent is most tempting and most dangerous —
diagnosing a broken system from logs and metrics is exactly what LLMs are good at, but a
lone agent that's *confidently wrong* will happily apply a fix that doesn't work, or report
success when nothing actually recovered. So this time, we wanted to prove — not just
claim — that a society with disagreement, staked confidence, and a referee grounded in
reality is dramatically more trustworthy than one agent working alone.

## What it does
Mayday runs an autonomous incident-response society against a real Laravel CRM (the
"patient"):

1. **A Watchman** patrols every page of the app. When one breaks, it opens an incident.
2. **A Dispatcher** classifies the failure and runs a **trust-weighted auction** — two
   investigator agents bid for the case, each bid weighted by how accurate that agent has
   been on this *category* of failure before.
3. **Two Investigators** — each with a *different* toolset, so they genuinely see different
   evidence — stake a root-cause hypothesis with a confidence bet, then **debate**: attack
   each other's conclusion citing live tool evidence, and hold or revise.
4. **A deterministic Adjudicator** doesn't pick the better argument — it **trials each
   proposed fix against the real health check** (apply → check → revert) and keeps only the
   one that actually heals the app.
5. **A Verifier** commits the cure: config fixes auto-apply; source-code fixes pause for a
   one-click human approval; anything that doesn't hold is rolled back.
6. **Trust settles** toward whoever was right, and a **case file** is written to memory —
   so the next incident of that kind is faster and surer. The society learns.

All of it streams live into a **War Room**: a siren, operator stations with the agents'
speech bubbles, trust bars, live MTTR, the human-approval modal, and the patient page
going down → back up in an embedded frame.

## The honesty guarantees (why the demo is real, not staged)
- Faults corrupt the app's **real state** — a value in a settings table, or a real
  source-code symbol. The fix repairs that same state, discovered from evidence.
- There's a private `faults` ledger for *grading only* — and **nothing that counts as the
  system working ever reads it**: not the app's routes, not its health check, not any
  agent or tool.
- "Resolved" means the adjudicator **applied a candidate fix and the real health check
  passed**. When nothing heals the patient, the society returns INCONCLUSIVE and escalates
  honestly instead of faking a win.

## How we built it
- **Patient:** Laravel 13 / PHP 8.4 CRM (login, dashboard, users/orders/reports). Eight
  fault injectors break real console pages — five config/state faults, three source-code
  faults — each with a clean clue trail in the logs.
- **Agents:** Python. An OpenAI-compatible client with a provider switch — local Ollama
  `qwen2.5` for development, **`qwen-max` on Qwen Cloud** (DashScope) for the real proof.
  The client is **quota-resilient**: if the active model's free pool is exhausted mid-run
  (403 `FreeTierOnly`), it fails over down a ping-validated chain of Qwen models
  (`qwen3.7-max` → `qwen3-max` → `qwen3.7-plus` → `qwen3.5-plus`) and continues the
  incident — every call's model is logged, so a failover is auditable, never silent.
- **Model Context Protocol (MCP):** the agents' *only* window into the patient is a
  seven-tool **MCP server** (`agents/mcp_server.py`) — `log.search`, `metrics.query`,
  `config.read`, `db.inspect`, `healthcheck.run`, `recent_errors`, `code.read/patch`, and
  `runbook.rag`. Investigators are each granted a *different subset* of these MCP tools,
  which is precisely what makes them see different evidence and disagree. The tools are the
  golden-rule firewall in code: they can touch the app's real state (settings, users,
  orders, source) but *never* the fault ledger. Trust and case memory persist in SQLite
  (Postgres-ready for prod).
- **War Room:** a dependency-free standard-library HTTP server with a Server-Sent-Events
  live feed — no framework to install, everything it shows is the real structured log the
  society writes as it runs.

## How it fits Track 3 (Agent Society)
- **Task decomposition:** Dispatcher → investigation brief → trust-weighted auction, with
  investigators split across different tools.
- **Conflict resolution:** staked debate resolved by a referee that *trials fixes against
  reality*, not rhetoric.
- **Efficiency over a single-agent baseline:** we ship the baseline (`baseline.py`) and a
  benchmark (`benchmark.py`) and measured it — see below.

## The proof (measured, on qwen-max)
Both modes ran **identical prompts, tools, and apply+verify path** — the only difference
is the society mechanism (auction + debate + adjudication + verify + memory):

| Mode | Resolved | Rate | Mean MTTR |
| --- | --- | --- | --- |
| **Society** | **6 / 8** | **75%** | 91.2s |
| Single-agent baseline | 2 / 8 | 25% | 40.0s |

**3× the resolution rate.** The society wins exactly where the mechanism matters — all
three code faults and the routing fault, where a lone agent gives up early or commits the
wrong fix. It trades ~50s of extra latency (debate + trial-and-revert) for that
reliability: the same tradeoff a real on-call org makes.

And the society **learns**: over five repeat incidents of one fault class (also measured,
`docs/learning-curve.json`), it resolved **5/5**, and per-category trust converged from a
neutral 0.5/0.5 split to **1.0/0.0** — the auction learns *which agent to trust* for each
failure class, while case-file memory primes every new investigation with the prior fix.

## Challenges we ran into
- **Keeping it honest.** The hardest engineering wasn't the agents — it was guaranteeing
  no diagnosis path could ever touch the fault ledger, and that "resolved" always meant a
  real health check passed. That constraint shaped the whole architecture.
- **A fair benchmark.** It's easy to make a society look good by giving it better prompts.
  We gave the single-agent baseline the *same* improved prompts and tools, so the measured
  delta is purely the mechanism.
- **A single-threaded dev server.** `php artisan serve` serializes requests, so a health
  check during an active fault could take ~10s; the War Room caches health in a background
  thread so the live UI never blocks.

## Accomplishments we're proud of
A multi-agent system where the "society" isn't decoration — it's *measurably* why the
system works, verified against a fair baseline on the real model. And a demo where every
single thing on screen is real: the break, the debate, the fix, the recovery.

## What we learned
Disagreement is a feature. A second agent with different tools and a stake in being right
catches the confident-but-wrong fixes that a lone agent commits — and a referee grounded
in reality (does the app actually recover?) is worth more than any amount of clever
argument.

## What's next
Deploy the patient + society to Alibaba Cloud (ECS + ApsaraDB RDS Postgres + OSS) so the
last environment-specific fault closes out in production; grow the fault catalog; and push
the learning curve further with richer case-file memory.

## Built with
Qwen (`qwen-max` on **Qwen Cloud / DashScope**; `qwen2.5` via Ollama for dev) · **Model
Context Protocol (MCP)** tool server · Alibaba Cloud **OSS** (report storage) · Laravel 13 ·
PHP 8.4 · Python · SQLite (ApsaraDB Postgres-ready) · Server-Sent Events · a
dependency-free stdlib War Room UI.

## Try it
Repo + full run instructions in the README. `python warroom.py`, pick a fault, hit
**Trigger incident**, and watch the society work.
