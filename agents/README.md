# Mayday — agents backend

Python side of Mayday: the **Watchman** (alarm), the **Coordinator** (state
machine + agent society, Days 3–5), and the MCP tool layer (Day 2).

## Watchman (built, no dependencies)

Patrols the whole patient system (every route from `GET /_watch/targets`, each
with its expected status) and opens an incident when pages stay sick for two
patrols in a row, then wakes the Coordinator. Detect-only — never diagnoses.

```bash
# 1) make sure the patient is running (in ../patient):  php artisan serve
# 2) run the watchman (stdlib only — no venv/pip needed):
python watchman.py
```

Then, in another shell, break the patient and watch the alarm fire:

```bash
cd ../patient
php artisan fault:inject route_renamed   # ~2 patrols later: INCIDENT OPENED
php artisan fault:clear                   # ~1 patrol later: INCIDENT RESOLVED (with MTTR)
```

Incidents are stored in `data/mayday.sqlite`; structured events (with token
counts later) go to `logs/coordinator.jsonl`.

## Agent society (Day 3+)

```bash
python -m venv venv && source venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env    # set QWEN_KEY etc. — BUILD on local, PROVE on Qwen
```
