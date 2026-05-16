"""
OpenAlpha - Quant — WorldQuant BRAIN API Client

Full pipeline:
  1. Authenticate (HTTP Basic Auth → session cookie)
  2. POST /simulations with alpha payload
  3. Poll Location header URL respecting Retry-After
  4. Extract real metrics (Sharpe, Fitness, Turnover, Returns, Correlation)
  5. Run IQC gate check on REAL metrics
  6. Return BrainResult with PASS/FAIL and gate details

Auth: email + password via HTTP Basic Auth.
Credentials stored in .env as BRAIN_EMAIL / BRAIN_PASSWORD.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

BRAIN_BASE = "https://api.worldquantbrain.com"
_AUTH_URL  = f"{BRAIN_BASE}/authentication"
_SIM_URL   = f"{BRAIN_BASE}/simulations"

# IQC real-metric hard gates
GATE_SHARPE_MIN   = 1.25
GATE_FITNESS_MIN  = 1.0
GATE_TURNOVER_MIN = 1.0
GATE_TURNOVER_MAX = 70.0


class BrainAuthError(Exception):
    """Raised when BRAIN authentication fails."""


class BrainSubmitError(Exception):
    """Raised when simulation submission fails."""


class BrainPollError(Exception):
    """Raised when polling fails after max retries."""


@dataclass
class BrainGateResult:
    """Results from real IQC gate checks on BRAIN simulation output."""
    passed: bool
    sharpe: Optional[float]        = None
    fitness: Optional[float]       = None
    turnover: Optional[float]      = None
    returns: Optional[float]       = None
    drawdown: Optional[float]      = None
    margin: Optional[float]        = None
    failures: list[str]            = field(default_factory=list)
    warnings: list[str]            = field(default_factory=list)
    alpha_id: Optional[str]        = None   # BRAIN alpha ID after submission
    simulation_status: str         = "UNKNOWN"


async def authenticate(email: str, password: str) -> httpx.Cookies:
    """
    Authenticate with BRAIN using HTTP Basic Auth.
    BRAIN returns HTTP 201 on success with session cookies.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _AUTH_URL,
            auth=(email, password),
        )
        # BRAIN returns 201 (Created) on successful auth
        if resp.status_code in (200, 201):
            logger.info("[brain] Authenticated as %s (HTTP %d)", email, resp.status_code)
            return resp.cookies
        else:
            body = _safe_json(resp)
            msg = body.get("message", resp.text[:200]) if body else resp.text[:200]
            raise BrainAuthError(
                f"BRAIN auth failed HTTP {resp.status_code}: {msg}"
            )


async def submit_and_poll(
    simulation_payload: dict,
    cookies: httpx.Cookies,
    max_poll_seconds: int = 300,
) -> BrainGateResult:
    """
    Submit a simulation to BRAIN and poll until complete.

    Args:
        simulation_payload: The dict from alpha's simulation_payload field.
                            Must include 'settings' and 'regular' keys.
        cookies: Auth cookies from authenticate().
        max_poll_seconds: Abort polling after this many seconds.

    Returns:
        BrainGateResult with all real metrics and gate pass/fail.
    """
    # Ensure type field is present (required by BRAIN API)
    # Required BRAIN API fields with IQC-compliant defaults
    _defaults = {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "decay": 6,          # BRAIN requires decay >= 1 when neutralization is set
            "neutralization": "INDUSTRY",
            "truncation": 0.08,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "OFF",
            "language": "FASTEXPR",
            "visualization": False,
        }
    }
    # Deep-merge: simulation_payload settings override defaults
    payload = dict(_defaults)
    payload["settings"] = {**_defaults["settings"], **simulation_payload.get("settings", {})}
    payload["regular"] = simulation_payload.get("regular", "")
    if "type" in simulation_payload:
        payload["type"] = simulation_payload["type"]


    async with httpx.AsyncClient(
        timeout=60.0,
        cookies=cookies,
        follow_redirects=False,
    ) as client:
        # ── 1. Submit simulation ────────────────────────────────────────────
        logger.info("[brain] Submitting simulation for expression: %s...",
                    payload.get("regular", "")[:60])

        sim_resp = await client.post(_SIM_URL, json=payload)

        if sim_resp.status_code not in (200, 201, 202):
            body = _safe_json(sim_resp)
            msg = body.get("message", sim_resp.text[:300]) if body else sim_resp.text[:300]
            raise BrainSubmitError(
                f"BRAIN simulation submit failed HTTP {sim_resp.status_code}: {msg}"
            )

        # BRAIN returns 201 + Location header pointing to progress URL
        location = sim_resp.headers.get("Location")
        if not location:
            # Sometimes result is inline on 200
            result_data = _safe_json(sim_resp) or {}
            return _extract_gate_result(result_data)

        # Make location absolute if relative
        if location.startswith("/"):
            location = BRAIN_BASE + location

        logger.info("[brain] Simulation submitted → polling: %s", location)

        # ── 2. Poll until done ──────────────────────────────────────────────
        elapsed = 0
        poll_count = 0

        while elapsed < max_poll_seconds:
            poll_resp = await client.get(location)

            if poll_resp.status_code == 200:
                data = _safe_json(poll_resp) or {}

                # Retry-After = 0 or absent means simulation is done
                retry_after_raw = poll_resp.headers.get("Retry-After", "0")
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = 0.0

                if retry_after == 0:
                    logger.info("[brain] Simulation complete after %ds / %d polls",
                                elapsed, poll_count)
                    return _extract_gate_result(data)

                wait = min(retry_after, 30.0)   # cap at 30s
                logger.info(
                    "[brain] Simulation running — Retry-After=%.0fs, elapsed=%ds",
                    retry_after, elapsed,
                )
                await asyncio.sleep(wait)
                elapsed += wait
                poll_count += 1

            elif poll_resp.status_code == 429:
                # Rate limited while polling — back off
                wait = float(poll_resp.headers.get("Retry-After", "10"))
                logger.warning("[brain] Rate limited while polling — waiting %.0fs", wait)
                await asyncio.sleep(wait)
                elapsed += wait

            else:
                body = _safe_json(poll_resp)
                msg = (body or {}).get("message", poll_resp.text[:200])
                raise BrainPollError(
                    f"Unexpected poll response HTTP {poll_resp.status_code}: {msg}"
                )

        raise BrainPollError(
            f"BRAIN simulation did not complete within {max_poll_seconds}s"
        )


def _extract_gate_result(data: dict) -> BrainGateResult:
    """
    Parse BRAIN simulation result JSON into a BrainGateResult.
    Handles ERROR status (unknown variable, syntax error, etc.) as gate FAIL.
    Runs all IQC hard gates on real (not estimated) metrics.
    """
    import math

    failures: list[str] = []
    warnings: list[str] = []

    sim_status = data.get("status", "UNKNOWN")
    alpha_id   = data.get("alpha") or data.get("id") or data.get("alphaId")
    error_msg  = data.get("message", "")

    # ── Handle ERROR status (e.g. unknown variable, syntax error) ───────────
    if sim_status == "ERROR":
        failure_msg = f"BRAIN simulation ERROR: {error_msg[:200]}"
        logger.warning("[brain] %s", failure_msg)
        return BrainGateResult(
            passed=False,
            failures=[failure_msg],
            warnings=[],
            alpha_id=alpha_id,
            simulation_status=sim_status,
        )

    # ── Extract real metrics ─────────────────────────────────────────────────
    # BRAIN result structure: metrics under 'is' (in-sample) key
    stats    = data.get("is", data.get("stats", {})) or {}

    sharpe   = _get_float(stats, ["sharpe", "sharpeRatio", "is_sharpe"])
    fitness  = _get_float(stats, ["fitness", "is_fitness"])
    turnover = _get_float(stats, ["turnover", "is_turnover"])
    returns  = _get_float(stats, ["returns", "is_returns", "annualizedReturn"])
    drawdown = _get_float(stats, ["drawdown", "maxDrawdown"])
    margin   = _get_float(stats, ["margin", "is_margin"])

    # Compute fitness from real numbers if not returned directly
    if fitness is None and sharpe is not None and returns is not None and turnover is not None:
        returns_dec  = abs(returns) / 100.0
        turnover_dec = turnover / 100.0
        denom        = max(turnover_dec, 0.125)
        fitness      = sharpe * math.sqrt(returns_dec) / denom

    # ── Gate checks on REAL metrics ─────────────────────────────────────────
    if sharpe is None:
        warnings.append("Sharpe not returned by BRAIN (check simulation completed)")
    elif sharpe < GATE_SHARPE_MIN:
        failures.append(
            f"REAL Sharpe {sharpe:.3f} < {GATE_SHARPE_MIN} — BRAIN gate FAIL"
        )
    elif sharpe < 1.35:
        warnings.append(f"REAL Sharpe {sharpe:.3f} marginal — target >1.35")

    if fitness is None:
        warnings.append("Fitness not returned (or could not be computed)")
    elif fitness <= GATE_FITNESS_MIN:
        failures.append(
            f"REAL Fitness {fitness:.3f} ≤ {GATE_FITNESS_MIN} — BRAIN gate FAIL"
        )

    if turnover is None:
        warnings.append("Turnover not returned by BRAIN")
    else:
        if turnover < GATE_TURNOVER_MIN:
            failures.append(
                f"REAL Turnover {turnover:.1f}% < {GATE_TURNOVER_MIN}% — BRAIN gate FAIL"
            )
        if turnover > GATE_TURNOVER_MAX:
            failures.append(
                f"REAL Turnover {turnover:.1f}% > {GATE_TURNOVER_MAX}% — BRAIN gate FAIL"
            )

    passed = len(failures) == 0

    logger.info(
        "[brain] Gate check: passed=%s sharpe=%.3f fitness=%.3f turnover=%.1f%%",
        passed,
        sharpe  or 0.0,
        fitness or 0.0,
        turnover or 0.0,
    )
    if failures:
        for f in failures:
            logger.warning("[brain] Gate FAIL: %s", f)

    return BrainGateResult(
        passed=passed,
        sharpe=sharpe,
        fitness=fitness,
        turnover=turnover,
        returns=returns,
        drawdown=drawdown,
        margin=margin,
        failures=failures,
        warnings=warnings,
        alpha_id=alpha_id,
        simulation_status=sim_status,
    )


def _safe_json(resp: httpx.Response) -> Optional[dict]:
    try:
        return resp.json()
    except Exception:
        return None


def _get_float(d: dict, keys: list[str]) -> Optional[float]:
    """Try multiple key names, return first float found."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None
