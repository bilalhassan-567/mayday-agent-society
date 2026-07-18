"""LLM client for the agent society.

Wraps the OpenAI-compatible endpoint resolved by config.llm_settings() (local
Ollama qwen2.5 in dev, qwen-max on Qwen Cloud in prod — switch via LLM_PROVIDER).

Responsibilities the plan mandates from call #1:
- log usage.prompt_tokens / completion_tokens to logs/tokens.jsonl (quota discipline)
- strict JSON parsing with ONE auto-repair retry (malformed-JSON risk mitigation)
- a tool-calling loop the Investigators drive
"""
import json
import threading
from pathlib import Path

from openai import OpenAI

import config
from tool_registry import call as call_tool
from tool_registry import schemas_for

ROOT = Path(__file__).resolve().parent
TOKENS_LOG = ROOT / "logs" / "tokens.jsonl"
ACTIVE_MODEL_FILE = ROOT / "logs" / "active_model.txt"

_S = config.llm_settings()
_client = OpenAI(base_url=_S["base_url"], api_key=_S["api_key"] or "x")
MODEL = _S["model"]
PROVIDER = _S["provider"]

# Every Qwen Cloud model has its OWN 1M-token free pool. If the active model's
# pool runs dry mid-run (403 AllocationQuota.FreeTierOnly — we run with
# Stop-on-Exhaust enabled so it errors instead of billing), fail over down a
# CHAIN of Qwen models — best/newest first, each ping-validated on this account —
# and stay on the working one for the rest of the process. Qwen-family only, so
# the Track-3 "built on Qwen" claim stays true through any failover.
# tokens.jsonl records the model per call, so every failover is auditable.
import os as _os
FALLBACK_MODELS = ([m.strip() for m in _os.environ.get(
    "QWEN_FALLBACK_MODELS",
    "qwen3.7-max-2026-06-08,qwen3-max,qwen3.7-plus,qwen3.5-plus-2026-02-15",
).split(",") if m.strip()] if PROVIDER == "qwen" else [])
_UNTRIED = list(FALLBACK_MODELS)  # consumed head-first as failovers happen

# Cross-process memory: a fresh process (a new `run_incident.py`, or the War Room
# restarting) would otherwise always retry MODEL first, re-eat the same 403, and
# only then fail over — on every single run, forever, once a model is dry. Instead,
# remember the last model that actually worked and start there next time, skipping
# the models ahead of it in FALLBACK_MODELS (they're presumed still dry too; a real
# quota reset next billing cycle just means editing/clearing this file).
if PROVIDER == "qwen" and ACTIVE_MODEL_FILE.exists():
    _remembered = ACTIVE_MODEL_FILE.read_text(encoding="utf-8").strip()
    if _remembered and _remembered in FALLBACK_MODELS:
        MODEL = _remembered
        _UNTRIED = FALLBACK_MODELS[FALLBACK_MODELS.index(_remembered) + 1:]


def _log_tokens(usage, tag: str, model: str) -> None:
    if usage is None:
        return
    TOKENS_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "provider": PROVIDER, "model": model, "tag": tag,
        "in": getattr(usage, "prompt_tokens", None),
        "out": getattr(usage, "completion_tokens", None),
    }
    with TOKENS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


# Investigators A/B (and their debate sides) run concurrently in separate threads,
# each calling chat() independently. MODEL/_UNTRIED are process-global, so advancing
# them on a quota-exhausted error must be serialized — otherwise two threads racing
# on the same dead model could both pop _UNTRIED and skip a model, or stomp each
# other's write to ACTIVE_MODEL_FILE.
_failover_lock = threading.Lock()


def chat(messages, tools=None, temperature=0.0, tag="chat", json_mode=False):
    global MODEL
    my_model = MODEL  # the model THIS call is actually using — never trust the
                       # global again after this point, another thread may advance it
    kwargs = {"model": my_model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if json_mode:
        # Forces the model to emit a single valid JSON object (Ollama & DashScope
        # both honor this via the OpenAI-compatible response_format).
        kwargs["response_format"] = {"type": "json_object"}
    while True:
        try:
            r = _client.chat.completions.create(**kwargs)
            break
        except Exception as e:
            # Free quota exhausted on this model — walk down the fallback chain.
            if "FreeTierOnly" not in str(e):
                raise
            with _failover_lock:
                if MODEL == my_model:
                    # first thread to discover my_model is dry -> advance the chain
                    while _UNTRIED and _UNTRIED[0] == MODEL:
                        _UNTRIED.pop(0)  # never retry the model that just ran dry
                    if not _UNTRIED:
                        raise  # chain exhausted — surface the quota error honestly
                    nxt = _UNTRIED.pop(0)
                    print(f"[llm] {MODEL} free quota exhausted -> failing over to {nxt}")
                    MODEL = nxt
                    ACTIVE_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
                    ACTIVE_MODEL_FILE.write_text(MODEL, encoding="utf-8")
                # else: another thread already advanced MODEL past my_model — adopt
                # it below instead of popping the chain again.
                my_model = MODEL
            kwargs["model"] = my_model
    _log_tokens(getattr(r, "usage", None), tag, my_model)
    return r


def extract_json(text: str):
    """Best-effort parse of a JSON object from model text (handles code fences)."""
    if not text or not text.strip():
        raise ValueError("empty response")
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(t[start:end + 1])
        raise


def _salvage(text: str) -> dict:
    """Last resort: regex-extract top-level "key": value pairs from broken JSON.
    Recovers the flat fields we need even when a nested field is malformed."""
    import re
    out = {}
    pattern = r'"(\w+)"\s*:\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null)'
    for m in re.finditer(pattern, text or ""):
        key, raw = m.group(1), m.group(2)
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw.strip('"')
    return out


def chat_json(messages, temperature=0.0, tag="json") -> dict:
    """Chat and return parsed JSON. JSON mode + one auto-repair retry + a regex
    salvage so a sloppy local model can never crash the pipeline."""
    r = chat(messages, temperature=temperature, tag=tag, json_mode=True)
    text = r.choices[0].message.content or ""
    try:
        return extract_json(text)
    except (ValueError, json.JSONDecodeError):
        repair = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "That was not valid JSON. Reply with ONLY a single valid "
                                        "JSON object; keep string values short and free of quotes."},
        ]
        r2 = chat(repair, temperature=0.0, tag=tag + ":repair", json_mode=True)
        text2 = r2.choices[0].message.content or ""
        try:
            return extract_json(text2)
        except (ValueError, json.JSONDecodeError):
            return _salvage(text2) or _salvage(text)


# Tools that must be scoped to the current incident. We FORCE the incident_id
# rather than trusting the model to pass it — a weak model that forgets would
# otherwise see a resolved incident's stale log lines / stack traces and be misled.
_INCIDENT_SCOPED_TOOLS = {"log_search", "recent_errors"}


def tool_loop(system: str, user: str, tool_names: list[str],
              max_steps: int = 6, tag: str = "agent", incident_id: int | None = None) -> dict:
    """Run a tool-calling loop. The model calls tools from its allowed subset until
    it stops requesting them. Returns {final_text, transcript} where transcript is
    the list of (tool, args, result) the agent actually gathered.

    If incident_id is given, it is force-injected into every incident-scoped tool
    call so stale cross-incident evidence can never leak in."""
    tools = schemas_for(tool_names)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    transcript = []

    for step in range(max_steps):
        r = chat(messages, tools=tools, tag=f"{tag}:step{step}")
        msg = r.choices[0].message
        calls = msg.tool_calls or []

        if not calls:
            return {"final_text": msg.content or "", "transcript": transcript}

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls
            ],
        })

        for c in calls:
            name = c.function.name
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if incident_id is not None and name in _INCIDENT_SCOPED_TOOLS:
                args["incident_id"] = incident_id   # force scoping, don't trust the model
            try:
                result = call_tool(name, **args)
            except Exception as e:  # tool failure is evidence too, not a crash
                result = {"error": str(e)}
            transcript.append({"tool": name, "args": args, "result": result})
            messages.append({
                "role": "tool", "tool_call_id": c.id,
                "content": json.dumps(result, default=str)[:4000],
            })

    # Ran out of tool steps — ask for the final answer with no tools.
    messages.append({"role": "user", "content": "Stop investigating. Give your final answer now."})
    r = chat(messages, tag=f"{tag}:final")
    return {"final_text": r.choices[0].message.content or "", "transcript": transcript}
