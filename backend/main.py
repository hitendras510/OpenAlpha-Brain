"""
OpenBrain Alpha — FastAPI Backend
WorldQuant BRAIN Alpha Generation Engine for IQC 2026
"""
from __future__ import annotations

import json
import uuid
import time
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import openai

from system_prompt import SYSTEM_PROMPT

app = FastAPI(title="OpenBrain Alpha Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory session store ─────────────────────────────────────────────────
# Stores: generated alphas, structural fingerprints, conversation history
session_store: dict[str, dict] = {}

def get_or_create_session(session_id: str) -> dict:
    if session_id not in session_store:
        session_store[session_id] = {
            "alphas": [],
            "fingerprints": [],
            "conversation_history": [],
            "family_run_tracker": [],
            "rejected_motifs": [],
            "created_at": time.time(),
        }
    return session_store[session_id]


# ─── Request / Response models ────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    session_id: str
    api_key: str
    model: str = "gpt-4o"
    family_hint: Optional[str] = None   # optional forced family
    count: int = 1                       # how many alphas to generate


class ResetRequest(BaseModel):
    session_id: str


class MetricsUpdate(BaseModel):
    session_id: str
    alpha_id: str
    real_sharpe: Optional[float] = None
    real_fitness: Optional[float] = None
    real_turnover: Optional[float] = None
    real_corr: Optional[str] = None
    status: Optional[str] = None  # "passed", "failed", "pending"


# ─── Helpers ─────────────────────────────────────────────────────────────────
def build_user_message(session: dict, family_hint: Optional[str]) -> str:
    fingerprints = session["fingerprints"]
    rejected = session["rejected_motifs"]
    families_used = session["family_run_tracker"][-3:] if session["family_run_tracker"] else []

    parts = ["Generate ONE new alpha that passes all IQC 2026 hard gates."]

    if fingerprints:
        fp_summary = json.dumps(fingerprints, indent=2)
        parts.append(
            f"\n\nFINGERPRINT MEMORY — avoid structural similarity with any of these:\n{fp_summary}"
        )

    if rejected:
        parts.append(
            f"\n\nREJECTED MOTIFS — never reuse these patterns:\n{json.dumps(rejected, indent=2)}"
        )

    if families_used and len(set(families_used)) == 1:
        parts.append(
            f"\n\nFAMILY LOCK WARNING: You have generated 3+ alphas in the '{families_used[0]}' family. "
            f"You MUST switch to a different factor family now."
        )

    if family_hint:
        parts.append(f"\n\nPREFERRED FAMILY: {family_hint} (use this unless it creates a fingerprint collision)")

    parts.append("\n\nRespond ONLY with the JSON object. No preamble, no markdown fences.")
    return "".join(parts)


def fingerprint_collision(new_fp: dict, existing_fps: list[dict]) -> bool:
    """Reject if new fingerprint shares ≥ 2 fields with any existing one."""
    keys = ["dataset", "topology", "temporal", "normalization", "direction", "neutral"]
    for fp in existing_fps:
        matches = sum(1 for k in keys if fp.get(k) == new_fp.get(k))
        if matches >= 2:
            return True
    return False


def call_llm(api_key: str, model: str, messages: list[dict]) -> str:
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.9,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.post("/api/generate")
async def generate_alpha(req: GenerateRequest):
    if req.count < 1 or req.count > 5:
        raise HTTPException(400, "count must be 1–5")

    session = get_or_create_session(req.session_id)
    results = []

    for _ in range(req.count):
        # Build conversation history context (last 6 turns max)
        history = session["conversation_history"][-6:]
        user_msg = build_user_message(session, req.family_hint)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = call_llm(req.api_key, req.model, messages)
            alpha = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(500, f"LLM returned invalid JSON: {raw[:300]}")
        except Exception as e:
            raise HTTPException(500, str(e))

        # Assign a unique runtime ID
        alpha["runtime_id"] = str(uuid.uuid4())[:8]
        alpha["generated_at"] = time.time()
        alpha["real_metrics"] = {
            "sharpe": None, "fitness": None, "turnover": None, "corr": None
        }
        alpha["status"] = "pending"

        fp = alpha.get("structural_fingerprint", {})

        # Anti-crowding check
        if fingerprint_collision(fp, session["fingerprints"]):
            alpha["collision_detected"] = True
            alpha["decision"] = "REJECT"
            session["rejected_motifs"].append(fp)
        else:
            alpha["collision_detected"] = False
            # Register fingerprint and family
            session["fingerprints"].append(fp)
            family = alpha.get("family", "Unknown")
            session["family_run_tracker"].append(family)

        # Store in session
        session["alphas"].append(alpha)

        # Update conversation history for continuity
        session["conversation_history"].append({"role": "user", "content": user_msg})
        session["conversation_history"].append({"role": "assistant", "content": raw})

        results.append(alpha)

    return {"session_id": req.session_id, "alphas": results, "total_in_session": len(session["alphas"])}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = get_or_create_session(session_id)
    return {
        "session_id": session_id,
        "alphas": session["alphas"],
        "fingerprints": session["fingerprints"],
        "rejected_count": len(session["rejected_motifs"]),
        "family_distribution": _family_dist(session["alphas"]),
        "created_at": session["created_at"],
    }


@app.post("/api/reset")
async def reset_session(req: ResetRequest):
    if req.session_id in session_store:
        del session_store[req.session_id]
    return {"reset": True, "session_id": req.session_id}


@app.post("/api/update-metrics")
async def update_metrics(update: MetricsUpdate):
    session = get_or_create_session(update.session_id)
    for alpha in session["alphas"]:
        if alpha.get("runtime_id") == update.alpha_id or alpha.get("alpha_id") == update.alpha_id:
            if update.real_sharpe is not None:
                alpha["real_metrics"]["sharpe"] = update.real_sharpe
            if update.real_fitness is not None:
                alpha["real_metrics"]["fitness"] = update.real_fitness
            if update.real_turnover is not None:
                alpha["real_metrics"]["turnover"] = update.real_turnover
            if update.real_corr is not None:
                alpha["real_metrics"]["corr"] = update.real_corr
            if update.status is not None:
                alpha["status"] = update.status
            return {"updated": True}
    raise HTTPException(404, "Alpha not found in session")


@app.get("/api/health")
async def health():
    return {"status": "ok", "sessions": len(session_store)}


def _family_dist(alphas: list) -> dict:
    dist: dict[str, int] = {}
    for a in alphas:
        f = a.get("family", "Unknown")
        dist[f] = dist.get(f, 0) + 1
    return dist


# ─── Serve frontend static files ─────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("../frontend/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
