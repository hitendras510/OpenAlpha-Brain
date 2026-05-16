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
    brain_checks: list[dict]       = field(default_factory=list)  # raw checks[] from BRAIN
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
    Parse BRAIN simulation/alpha result JSON into a BrainGateResult.
    
    BRAIN API returns simulation results with the alpha registered under data["alpha"].
    Real metrics are under data["is"] (in-sample).
    Gate checks are under data["is"]["checks"].
    """
    import math

    failures: list[str] = []
    warnings: list[str] = []

    sim_status = data.get("status", "UNKNOWN")
    # Alpha ID is in "alpha" field of simulation result, or "id" of alpha record
    alpha_id   = data.get("alpha") or data.get("id")
    error_msg  = data.get("message", "")

    # ── Handle ERROR status (unknown variable, syntax error, etc.) ───────────
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

    # ── Extract real metrics from "is" (in-sample) section ──────────────────
    # Confirmed field names from live BRAIN API response
    is_data = data.get("is", {}) or {}

    sharpe   = _get_float(is_data, ["sharpe"])
    fitness  = _get_float(is_data, ["fitness"])
    turnover = _get_float(is_data, ["turnover"])   # decimal (0.35 = 35%)
    returns  = _get_float(is_data, ["returns"])    # decimal (-0.12 = -12%)
    drawdown = _get_float(is_data, ["drawdown"])
    margin   = _get_float(is_data, ["margin"])

    # Convert decimal turnover to percentage for consistency with our gates
    turnover_pct = (turnover * 100) if turnover is not None else None
    returns_pct  = (returns  * 100) if returns  is not None else None

    # ── Parse BRAIN's own gate checks[] array ────────────────────────────────
    brain_checks = is_data.get("checks", [])
    for chk in brain_checks:
        name   = chk.get("name", "")
        result = chk.get("result", "")
        value  = chk.get("value")
        limit  = chk.get("limit")

        if result == "FAIL":
            failures.append(
                f"BRAIN gate {name} FAIL: value={value} limit={limit}"
            )
        elif result == "PENDING":
            warnings.append(f"BRAIN gate {name} still PENDING (correlation check)")

    # ── Log real metrics ──────────────────────────────────────────────────────
    logger.info(
        "[brain] Simulation COMPLETE — sharpe=%.3f fitness=%.3f turnover=%.1f%% returns=%.1f%%",
        sharpe   or 0.0,
        fitness  or 0.0,
        turnover_pct or 0.0,
        returns_pct  or 0.0,
    )

    # If BRAIN's own checks had failures → mark as FAIL
    # If no checks returned (status != COMPLETE), use our gate thresholds
    if not brain_checks and sharpe is not None:
        if sharpe < GATE_SHARPE_MIN:
            failures.append(f"REAL Sharpe {sharpe:.3f} < {GATE_SHARPE_MIN}")
        if fitness is not None and fitness <= GATE_FITNESS_MIN:
            failures.append(f"REAL Fitness {fitness:.3f} ≤ {GATE_FITNESS_MIN}")
        if turnover_pct is not None:
            if turnover_pct < GATE_TURNOVER_MIN:
                failures.append(f"REAL Turnover {turnover_pct:.1f}% < {GATE_TURNOVER_MIN}%")
            if turnover_pct > GATE_TURNOVER_MAX:
                failures.append(f"REAL Turnover {turnover_pct:.1f}% > {GATE_TURNOVER_MAX}%")

    if failures:
        for f in failures:
            logger.warning("[brain] Gate FAIL: %s", f)

    passed = len(failures) == 0

    return BrainGateResult(
        passed=passed,
        sharpe=sharpe,
        fitness=fitness,
        turnover=turnover_pct,
        returns=returns_pct,
        drawdown=drawdown,
        margin=margin,
        failures=failures,
        warnings=warnings,
        brain_checks=brain_checks,       # pass raw checks[] through
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
