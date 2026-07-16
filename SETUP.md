# SETUP.md — first-time bring-up on a new machine

Get Mayday running from a clean checkout. For the mental model and how the pieces fit,
read [`CLAUDE.md`](CLAUDE.md). Two processes run side by side: the **patient** (Laravel,
:8000) and the **War Room** (Python, :8800).

## Prerequisites
- **PHP 8.4** with the `pdo_sqlite` and `sqlite3` extensions.
- **Composer**.
- **Python 3.10+**.
- One LLM provider:
  - **Ollama** for local dev: `ollama pull qwen2.5:7b`, or
  - a **Qwen Cloud** (DashScope) API key for `qwen-max` (the proof model).
- Windows + Laragon is the reference environment, but any OS works.

> **Laragon/PHP gotcha:** the `pdo_sqlite` / `sqlite3` DLLs ship with PHP but are often
> commented out in `php.ini`. If `php artisan migrate` reports `could not find driver`,
> uncomment `extension=pdo_sqlite` and `extension=sqlite3` in the active `php.ini`
> (`php --ini` prints its path), then restart the shell.

## 1. Patient (Laravel target)
```bash
cd patient
composer install
cp .env.example .env
php artisan key:generate            # fills APP_KEY (a secret — never commit .env)
# Ensure the SQLite DB file exists (dev uses SQLite):
#   Git Bash / macOS / Linux:  touch database/database.sqlite
#   PowerShell:                 New-Item -ItemType File database/database.sqlite
php artisan migrate --seed          # creates tables + seeds admin@example.com / password
php artisan serve --host=127.0.0.1 --port=8000
```
Verify: `curl http://127.0.0.1:8000/health` returns `{"status":"ok", ...}` with all
checks green. Operator console login: `admin@example.com` / `password`.

> If migrate can't find the DB, set an absolute path in `patient/.env`:
> `DB_DATABASE=C:/laragon/www/Hackathon/patient/database/database.sqlite` (forward slashes).

## 2. Agents (Python society)
```bash
cd agents
python -m venv venv
# activate:  source venv/Scripts/activate  (Git Bash)  |  venv\Scripts\activate  (PowerShell)
pip install -r requirements.txt
cp .env.example .env
```
Edit `agents/.env`:
- `PATIENT_URL=http://127.0.0.1:8000`
- For local dev: `LLM_PROVIDER=local` (Ollama on :11434).
- For the real proof: `LLM_PROVIDER=qwen`, `QWEN_KEY=sk-...`,
  `QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, `QWEN_MODEL=qwen-max`.

## 3. Run the War Room
```bash
cd agents && python warroom.py      # → open http://127.0.0.1:8800
```
The patient (step 1) must be running. In the UI: pick a fault → **Trigger incident** →
watch the society diagnose, debate, verify, and settle trust live. Config fixes
auto-apply; code fixes pause for a human-approval click.

## 4. Smoke test (confirm it all works end to end)
```bash
# CLI incident
cd patient && php artisan fault:inject db_pool_exhausted
cd ../agents && python run_incident.py --auto      # should resolve + heal /health

# Benchmark (society vs single-agent baseline; resumable from a checkpoint)
python benchmark.py                                # writes docs/benchmark-results.json
```

## Optional: UI tests
`pip install selenium` (dev-only, not in requirements.txt) + headless Chrome. Selenium
4.4+ auto-manages chromedriver. Test scripts are kept in a scratchpad, not the repo.

## What's NOT covered here
Cloud deployment (Alibaba ECS + ApsaraDB RDS Postgres + OSS) is the remaining "final
stage" — see the Phase C notes in [`CLAUDE.md`](CLAUDE.md) and [`docs/dev/PLAN.md`](docs/dev/PLAN.md).
