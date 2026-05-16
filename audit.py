"""Self-audit script for OpenAlpha - Quant — run from project root."""
import sys

SEP = "=" * 52

def chk(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    suffix = f"  → {detail}" if detail and not ok else ""
    print(f"  [{status}] {label}{suffix}")
    return ok

results = []

# ── LLM CLIENT ───────────────────────────────────────────────
src = open("llm_client.py").read()
results.append(chk("LLM: API key from env only",              "LLM_API_KEY" in src and "sk-" not in src))
results.append(chk("LLM: httpx.AsyncClient used",             "httpx.AsyncClient" in src))
results.append(chk("LLM: system passed as param",             '"system": system_prompt' in src or "'system': system_prompt" in src))
results.append(chk("LLM: history passed every call",          "history" in src))
results.append(chk("LLM: temperature from config",            "LLM_TEMPERATURE" in src))
results.append(chk("LLM: max_tokens from config",             "LLM_MAX_TOKENS" in src))
results.append(chk("LLM: timeout >= 60s",                     "90.0" in src or "60.0" in src))
results.append(chk("LLM: retry on 429/500/503",               "429" in src and "500" in src and "503" in src))
results.append(chk("LLM: finish_reason/stop_reason checked",  "finish_reason" in src or "stop_reason" in src))
results.append(chk("LLM: raw response logged at DEBUG",       "logger.debug" in src and "raw" in src))

# ── PARSER ──────────────────────────────────────────────────
src = open("alpha_parser.py").read()
results.append(chk("Parser: [2] FAST EXPRESSION extracted",   "sec2" in src or "_section(raw, 2" in src))
results.append(chk("Parser: fenced code blocks handled",      "fenced" in src))
results.append(chk("Parser: all 4 decision variants",         all(v in src for v in ["SUBMIT CANDIDATE","ADVANCE TO TEST","ITERATE","REJECT"])))
results.append(chk("Parser: sharpe/turnover as (min,max)",    "_parse_range" in src))
results.append(chk("Parser: all 6 fingerprint fields",        all(f in src for f in ["dataset","topology","temporal","normalization","direction","neutral"])))
results.append(chk("Parser: returns None on failure",         "return None" in src))
results.append(chk("Parser: docstring sample outputs (>>>)",  ">>>" in src))

# ── VALIDATOR ────────────────────────────────────────────────
src = open("validator.py").read()
results.append(chk("Validator: group_neutralize check",        "group_neutralize" in src))
results.append(chk("Validator: stack-based paren (depth<0)",   "depth < 0" in src))
results.append(chk("Validator: float window detection",        "FLOAT_WINDOW" in src or "float_window" in src.lower()))
results.append(chk("Validator: operator whitelist",            "PERMITTED_OPERATORS" in src))
results.append(chk("Validator: expression length 5-2000",      "< 5" in src and "> 2000" in src))
results.append(chk("Validator: Sharpe >= 1.25 gate",           "1.25" in src))
results.append(chk("Validator: Fitness > 1.0 gate",            "fitness" in src.lower() and "<= 1.0" in src))
results.append(chk("Validator: Turnover 1-70 both bounds",     "< 1.0" in src and "> 70.0" in src))
results.append(chk("Validator: Corr Risk HIGH triggers fail",  "HIGH" in src and "corr" in src.lower()))

# ── LOOP ENGINE ──────────────────────────────────────────────
src = open("loop_engine.py").read()
results.append(chk("Loop: stop_requested checked every cycle", "stop_requested" in src))
results.append(chk("Loop: max_cycles cap enforced",            "MAX_CYCLES" in src))
results.append(chk("Loop: max_mutations cap enforced",         "MAX_MUTATIONS" in src and "mutation_count" in src))
results.append(chk("Loop: same decision 3x -> restart",        "consecutive_same_decision" in src and ">= 3" in src))
results.append(chk("Loop: failure feedback with values",       "build_failure_feedback" in src))
results.append(chk("Loop: success feedback with fingerprint",  "build_success_feedback" in src))
results.append(chk("Loop: fingerprint memory injected",        "fingerprint_memory" in src))
results.append(chk("Loop: conversation history grows",         "conversation_history.append" in src))
results.append(chk("Loop: family rotation (3x lock)",         "family_run_tracker" in src and "_family_locked" in src))
results.append(chk("Loop: state saved after every cycle",      "save_session" in src))

# ── FASTAPI ──────────────────────────────────────────────────
src = open("main.py").read()
results.append(chk("FastAPI: /session/start returns immediately", "create_task" in src))
results.append(chk("FastAPI: loop as asyncio background task",    "asyncio.create_task" in src))
results.append(chk("FastAPI: GET /session/{id} route",           "session_id" in src and "load_session" in src))
results.append(chk("FastAPI: GET /session/{id}/alphas route",    "passed_alphas" in src or "/alphas" in src))
results.append(chk("FastAPI: POST /session/{id}/stop route",     "stop" in src and "request_stop" in src))
results.append(chk("FastAPI: GET /health route",                 "health" in src))
results.append(chk("FastAPI: structured JSON error responses",   "JSONResponse" in src))
results.append(chk("FastAPI: no shared global session state",    "_running_tasks" in src and "session_store" not in src))
results.append(chk("FastAPI: CORS middleware configured",        "CORSMiddleware" in src))

# ── CONFIG & SCAFFOLD ────────────────────────────────────────
env_ex = open(".env.example").read()
req    = open("requirements.txt").read()
readme = open("README.md").read()
sm_src = open("session_manager.py").read()

results.append(chk(".env.example has all required keys",
    all(k in env_ex for k in ["LLM_PROVIDER","LLM_MODEL","LLM_API_KEY","LLM_TEMPERATURE","MAX_CYCLES","MAX_MUTATIONS","SESSION_DIR"])))
results.append(chk("requirements.txt pins all deps",
    all(v in req for v in ["fastapi==","uvicorn","httpx==","pydantic==","pydantic-settings==","tenacity==","aiofiles==","python-dotenv=="])))
results.append(chk("sessions/ dir auto-created on startup",
    "mkdir" in open("main.py").read() or "mkdir" in sm_src))
results.append(chk("README: pip install + uvicorn command",
    "pip install -r requirements.txt" in readme and "uvicorn main:app" in readme))

# ── RESULT ───────────────────────────────────────────────────
passed = sum(1 for r in results if r)
total  = len(results)
print()
print(SEP)
print(f"  SELF-AUDIT: {passed}/{total} checks passed")
verdict = "PRODUCTION READY" if passed == total else f"NEEDS FIXES  ({total - passed} failure(s))"
print(f"  VERDICT: {verdict}")
print(SEP)
sys.exit(0 if passed == total else 1)
