# Mayday — an autonomous AI incident-response society

**Global AI Hackathon with Qwen Cloud · Track 3: Agent Society**

Mayday is a society of AI agents that watch a live web app, and when it breaks,
they **bid** for the case, **argue** over the root cause with staked confidence,
**verify** a fix against real health checks, and **settle trust** so the society
measurably improves over time. Every fix repairs the app's *real* state — no
scripted answers, no peeking at the fault key.

> A Watchman patrols the app. A fault hits. The Dispatcher runs a trust-weighted
> auction. Two Investigators reach opposite conclusions and **debate**, each citing
> live tool evidence. A deterministic Adjudicator **trials each proposed fix against
> the real health checks** and keeps only what actually works. Trust is awarded to
> whoever was right — and the next incident of that kind resolves faster. All of it
> streams live into a **War Room**.

---

## Why this fits Track 3

Track 3 asks for a multi-agent system with **task decomposition**, **conflict
resolution**, and **efficiency gains over a single-agent baseline**:

| Track-3 requirement | How Mayday does it |
| --- | --- |
| Task decomposition | Dispatcher decomposes the alert into an investigation brief + a **trust-weighted auction**; each Investigator gets a different tool subset, so they explore different slices of the truth. |
| Conflict resolution | Investigators **debate** with staked confidence; a deterministic **Adjudicator** resolves it by *trialing each fix against real health checks* (apply → check → revert) — the winner is what actually heals the patient, not who argued best. |
| Efficiency over single-agent | Ships a **single-agent baseline** (`baseline.py`) and a **benchmark** (`benchmark.py`) that runs both over the same faults; the society's second opinion + adjudication catch wrong fixes a lone agent commits, and **case-file memory + trust** make repeat incidents faster (learning curve). |

---

## The honesty guarantees (why the demo is real, not staged)

- The **fault injector** corrupts the app's *real* state (a config value in
  `app_settings`, or a real source-code symbol). The **fix repairs that same state**,
  discovered from evidence.
- The **`faults` ledger is never read** by the patient's routes, `/health`, or any
  agent/tool — it exists only to *grade* the run.
- The Adjudicator picks the winner by **applying each candidate fix and running the
  real health check**, then reverting — so "resolved" means the app genuinely came back.
- When no proposed fix heals the patient, the society returns **INCONCLUSIVE** and
  **escalates honestly** (re-investigate or roll back) rather than faking a success.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full diagram. In short:

```
Watchman ──patrols──> Patient (Laravel CRM console)         ┌─ MCP tool layer ─┐
   │ opens incident                                          │ log.search        │
   ▼                                                          │ metrics.query     │
Coordinator ── Dispatcher (auction) ── Investigator A ─┐      │ config.read       │
   │                                   Investigator B ─┤──────│ db.inspect        │
   │                                        (debate)   │      │ healthcheck.run   │
   ├─ Adjudicator (trial each fix vs real health) ─────┘      │ recent_errors     │
   ├─ Verifier (apply · re-check · rollback / human gate)     │ code.read/patch   │
   ├─ Trust store (per-agent, per-category)                   │ runbook.rag       │
   └─ Case-file memory (recall similar past incidents)        └───────────────────┘
                         │
                         ▼
                    War Room (live SSE UI)
```

- **Patient** — a real Laravel CRM (login, dashboard, users/orders/reports CRUD).
  8 faults break real console pages (5 config/state, 3 source-code).
- **Agents** — Python; OpenAI-compatible client that runs on **Qwen** (local Ollama
  `qwen2.5` for dev, **`qwen-max` on Qwen Cloud** for the real proof).
- **War Room** — dependency-free live console (SSE): siren, operator stations with
  speech bubbles, trust bars, MTTR, human-approval modal, auto-recovery.

---

## Run it locally

Prereqs: PHP 8.4 + SQLite, Python 3.10+, and either Ollama (`ollama pull qwen2.5:7b`)
or a Qwen Cloud key.

```bash
# 1) Patient app
cd patient && php artisan migrate --seed && php artisan serve --host=127.0.0.1 --port=8000

# 2) Agents — pick the model provider in agents/.env
#    local:  LLM_PROVIDER=local   (Ollama qwen2.5)
#    cloud:  LLM_PROVIDER=qwen    + QWEN_KEY=sk-...   (qwen-max on Qwen Cloud)

# 3) War Room (live UI)
cd agents && python warroom.py          # http://127.0.0.1:8800

# Or drive one incident from the CLI:
cd patient && php artisan fault:inject db_pool_exhausted
cd agents && python run_incident.py --auto
```

In the War Room: pick a fault → **Trigger incident** → watch the society diagnose,
debate, verify, and settle trust live. Config fixes auto-apply; source-code fixes
pause for a **human-approval** click.

---

## Benchmark (efficiency over single-agent)

```bash
cd agents
python benchmark.py                       # society vs single-agent baseline, all faults
python benchmark.py --learning db_pool_exhausted   # repeat a fault → learning curve
```

Writes `docs/benchmark-results.json` (resolution rate + mean MTTR for each). Headline
result on **`qwen-max`**, both modes running identical prompts, tools, and apply+verify
path (so the delta is the *mechanism*, not prompt tuning):

| Mode | Resolved | Rate | Mean MTTR |
| --- | --- | --- | --- |
| **Society** | **6 / 8** | **75%** | 91.2s |
| Single-agent baseline | 2 / 8 | 25% | 40.0s |

**3× the resolution rate.** The society wins exactly where the mechanism matters — all
three code faults and the routing fault, where a lone agent bails early or commits the
wrong fix. It trades ~50s of extra latency (debate + trial-and-revert) for that
reliability, the same tradeoff a real on-call org makes.

**Learning curve** (`docs/learning-curve.json`, 5 repeat incidents of one fault class,
qwen-max): **5/5 resolved**, and per-category trust converges from a neutral 0.5/0.5 split
to **1.0/0.0** — the auction learns *which agent to trust* for that failure class, while
case-file memory primes every new brief with the prior fix. (MTTR stays ~80–97s — flat,
since model latency dominates; we report that honestly rather than claim a speed-up.)

---

## Tested

- `agents/` deterministic engine test — modules, all 8 faults (inject → break →
  fix → healthy), tools, trust, memory, incident store, adjudication + escalation.
- War Room UI — Selenium assertions (no journal resurrection, live auto-recovery,
  approval + unresolved modals, full-incident render) + a full live end-to-end run.

## Honest limitations

- Local `qwen2.5:7b` is slow (~10 min/incident) and occasionally picks a wrong
  value on the hardest faults; `qwen-max` is fast and accurate. All headline numbers
  are produced on Qwen Cloud.
- Two faults' *fix values* are environment-specific (a DB host, a cloud key); their
  runbooks carry the correct value per environment.
- Structural breaks (deleting code) are out of auto-repair scope by design — the
  society escalates to rollback + human, rather than hallucinate a reconstruction.

## License

MIT — see [`LICENSE`](LICENSE).
