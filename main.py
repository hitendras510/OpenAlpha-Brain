"""
OpenAlpha - Quant — FastAPI Application
All routes return immediately. The generation loop runs as a background asyncio task.
"""
from __future__ import annotations

import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from models import SessionStatus, StartSessionRequest
import session_manager as sm
import loop_engine

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("openalpha")

# Track running loop tasks so we can check their status
_running_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure sessions directory exists on startup
    settings.SESSION_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("OpenAlpha - Quant started — sessions dir: %s", settings.SESSION_DIR)
    if not settings.LLM_API_KEY:
        logger.warning(
            "LLM_API_KEY is not set! Sessions will ERROR when the loop tries to call the LLM. "
            "Set it in your .env file."
        )
    yield
    # Cancel any still-running loops on shutdown
    for sid, task in list(_running_tasks.items()):
        if not task.done():
            task.cancel()
            logger.info("Cancelled running loop for session %s on shutdown", sid)


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OpenAlpha - Quant",
    version="1.0.0",
    description="Autonomous WorldQuant BRAIN Alpha Generation Engine — IQC 2026",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve single-file dashboard at /static/index.html
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "sessions_active": len(_running_tasks)}


@app.post("/session/start")
async def start_session(req: StartSessionRequest):
    """
    Create a new session and immediately fire the generation loop as a background task.
    Returns session_id without waiting for any LLM call.
    """
    state = await sm.create_session(focus_area=req.focus_area)
    sid = state.id

    # Launch loop as independent asyncio task — route returns immediately
    task = asyncio.create_task(
        _run_loop_safe(sid),
        name=f"loop-{sid}",
    )
    _running_tasks[sid] = task

    logger.info("Session %s started, focus_area=%r", sid, req.focus_area)
    return {"session_id": sid, "status": SessionStatus.IDLE}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """Return full session state snapshot (loaded fresh from disk)."""
    state = await sm.load_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return state.model_dump(mode="json")


@app.get("/session/{session_id}/alphas")
async def get_alphas(session_id: str):
    """Return only the list of passed alphas for the session."""
    state = await sm.load_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {
        "session_id": session_id,
        "count": len(state.passed_alphas),
        "alphas": [a.model_dump(mode="json") for a in state.passed_alphas],
    }


@app.post("/session/{session_id}/stop")
async def stop_session(session_id: str):
    """
    Set stop_requested flag on the session.
    The loop checks this flag at the top of every cycle and exits cleanly.
    """
    found = await sm.request_stop(session_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"stopped": True, "session_id": session_id}


# ── Serve dashboard at root ────────────────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    """Redirect root to the single-file dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


# ── Error handler ──────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": str(exc),
            "session_id": None,
            "cycle": None,
        },
    )


# ── Safe loop wrapper ──────────────────────────────────────────────────────────
async def _run_loop_safe(session_id: str) -> None:
    """Wraps run_loop to catch any unhandled exceptions and mark session ERROR."""
    try:
        await loop_engine.run_loop(session_id)
    except asyncio.CancelledError:
        logger.info("[%s] Loop task cancelled", session_id)
        await sm.update_status(session_id, SessionStatus.STOPPED)
    except Exception as exc:
        logger.error("[%s] Unhandled loop exception: %s", session_id, exc, exc_info=True)
        state = await sm.load_session(session_id)
        if state:
            state.status = SessionStatus.ERROR
            state.error_message = str(exc)
            await sm.save_session(state)
    finally:
        _running_tasks.pop(session_id, None)
