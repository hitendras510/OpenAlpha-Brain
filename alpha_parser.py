"""
OpenAlpha - Quant — Alpha Output Parser
Extracts all 8 fields (v2) from LLM-generated alpha text using non-greedy regex.
Returns None gracefully on any parse failure — caller decides how to handle.

Docstring test cases (run with: python -m doctest alpha_parser.py -v)

>>> sample1 = '''
... [1] ECONOMIC RATIONALE
...     Volume divergence from price signals smart-money accumulation.
... [2] FAST EXPRESSION
...     group_neutralize(rank(ts_delta(rank(volume / ts_mean(volume, 20)), 5)), industry)
... [3] ESTIMATED METRICS
...     Sharpe:    1.45
...     Fitness:   1.20
...     Turnover:  18%
...     Returns:   22%
...     Corr Risk: LOW
... [4] STRUCTURAL FINGERPRINT
...     Dataset:       Price/Vol
...     Topology:      NestedNonlinear
...     Temporal:      medium
...     Normalization: Rank
...     Neutralization: industry
... [5] AST TOPOLOGY HASH
...     Pattern: Rank(TSDelta(Rank(Divide), Int))
...     Collision check: NONE
... [6] REFINEMENT LOG
...     Original idea: raw volume ratio. Fixed by adding ts_delta layer.
... [7] DECISION
...     [ SUBMIT CANDIDATE ]
... [8] SIMULATION PAYLOAD
...     {"settings": {"delay": 1, "decay": 5}, "regular": "group_neutralize(...)"}
... '''
>>> result = parse_alpha_output(sample1)
>>> result is not None
True
>>> result['decision']
'SUBMIT CANDIDATE'
>>> result['metrics']['sharpe_min']
1.45
>>> result['ast_topology']
'Rank(TSDelta(Rank(Divide), Int))'

>>> sample2 = "malformed output with no fields at all"
>>> parse_alpha_output(sample2) is None
True
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Section boundary anchors ──────────────────────────────────────────────────
# Matches [N] header or ━━━ ALPHA [N] ━━━ dividers
_SEC = r"\[{n}\][^\n]*\n"


def _between(text: str, start_marker: str, end_marker: str) -> str:
    """Extract text between two section markers, stripped."""
    pattern = re.compile(
        re.escape(start_marker) + r"(.*?)" + re.escape(end_marker),
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _section(text: str, num: int, next_num: int | None = None) -> str:
    """Return the body of section [num], stopping at [next_num] or end of string."""
    start_pat = rf"\[{num}\][^\n]*\n"
    if next_num is not None:
        end_pat = rf"\[{next_num}\]"
        pattern = re.compile(start_pat + r"(.*?)" + end_pat, re.DOTALL)
    else:
        pattern = re.compile(start_pat + r"(.*?)$", re.DOTALL)
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _extract_expression(sec2_body: str) -> Optional[str]:
    """
    Extract the BRAIN expression from section [2].
    Handles fenced (```...```), inline backtick, and raw multiline formats.
    For multiline expressions (e.g. group_neutralize spanning multiple lines),
    joins and collapses whitespace.
    """
    # 1. Fenced code block
    fenced = re.search(r"```(?:\w+)?\s*\n?(.*?)```", sec2_body, re.DOTALL)
    if fenced:
        return " ".join(fenced.group(1).strip().split())

    # 2. Inline backtick
    inline = re.search(r"`([^`]+)`", sec2_body)
    if inline:
        return inline.group(1).strip()

    # 3. Multiline raw body: collapse all whitespace, keep as single expression
    stripped = sec2_body.strip()
    if stripped and ("group_neutralize" in stripped or "rank(" in stripped or "ts_" in stripped):
        # Join lines, collapse all whitespace sequences to single space
        joined = " ".join(stripped.split())
        return joined

    # 4. Single-line fallback
    for line in sec2_body.splitlines():
        line = line.strip()
        if line and ("group_neutralize" in line or "rank(" in line or "ts_" in line):
            return line

    return None


def _parse_range(text: str, label: str) -> tuple[Optional[float], Optional[float]]:
    """
    Parse 'Label: 1.30-1.60' or 'Label: 1.45' or 'Label: 21%' into (min, max) floats.
    Handles ASCII hyphen, en-dash, em-dash as range separators.
    Strips trailing % from captured numbers.
    """
    pattern = re.compile(
        label + r"[:\s]+([\d.]+)%?\s*(?:[-\u2013\u2014]\s*([\d.]+)%?)?",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m or not m.group(1):  # guard against empty captures
        return None, None
    try:
        lo = float(m.group(1))
    except (ValueError, TypeError):
        return None, None
    try:
        hi = float(m.group(2)) if m.group(2) else lo
    except (ValueError, TypeError):
        hi = lo
    return lo, hi


def _parse_corr_risk(text: str) -> Optional[str]:
    """Extract LOW | MEDIUM | HIGH from Corr Risk line."""
    m = re.search(r"Corr(?:elation)?\s*Risk\s*[:\s]+(LOW|MEDIUM|HIGH)", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _parse_fingerprint(sec4_body: str) -> dict:
    """Extract structural fingerprint fields. v2 uses 5-dim (drops direction, adds neutral)."""
    fields = {
        "dataset": r"Dataset\s*:\s*(.+)",
        "topology": r"Topology\s*:\s*(.+)",
        "temporal": r"Temporal\s*:\s*(.+)",
        "normalization": r"Normalization\s*:\s*(.+)",
        "direction": r"Direction\s*:\s*(.+)",
        # v2: neutralization (preferred) or neutral (v1 compat)
        "neutral": r"Neutral(?:ization)?\s*:\s*(.+)",
    }
    result = {}
    for key, pattern in fields.items():
        m = re.search(pattern, sec4_body, re.IGNORECASE)
        result[key] = m.group(1).strip().split("—")[0].strip() if m else None
    return result


def _parse_ast_topology(sec5_body: str) -> tuple[Optional[str], list[str]]:
    """
    v2: Extract AST topology pattern and collision list from [5] AST TOPOLOGY HASH.
    Returns (pattern_str, collision_list).
    """
    pattern_m = re.search(r"Pattern\s*:\s*(.+)", sec5_body, re.IGNORECASE)
    topology = pattern_m.group(1).strip() if pattern_m else None

    collision_m = re.search(r"Collision\s*check\s*:\s*(.+)", sec5_body, re.IGNORECASE)
    collision_raw = collision_m.group(1).strip() if collision_m else ""
    # If "NONE" or empty — no collisions
    if not collision_raw or collision_raw.upper() == "NONE":
        collisions = []
    else:
        # Split on comma or semicolon
        collisions = [c.strip() for c in re.split(r"[,;]", collision_raw) if c.strip()]
    return topology, collisions


def _parse_simulation_payload(sec8_body: str) -> Optional[dict]:
    """
    v2: Extract the JSON simulation payload from [8] SIMULATION PAYLOAD.
    Returns parsed dict or None.
    """
    import json
    # Try to find a JSON object in the section body
    json_m = re.search(r"(\{[\s\S]+\})", sec8_body)
    if not json_m:
        return None
    try:
        return json.loads(json_m.group(1))
    except json.JSONDecodeError:
        return None


def _parse_returns(sec3_body: str) -> Optional[float]:
    """v2: Extract annualized returns estimate from [3] ESTIMATED METRICS."""
    # Matches: 'Returns: 22%' or 'Returns: 22.5 %'
    m = re.search(r"Returns\s*[:\s]+([\d.]+)\s*%?", sec3_body, re.IGNORECASE)
    return float(m.group(1)) if m else None


def _parse_decision(sec6_body: str) -> Optional[str]:
    """Extract one of the 4 valid decision labels."""
    # Accept both [ LABEL ] and bare LABEL
    variants = [
        "SUBMIT CANDIDATE",
        "ADVANCE TO TEST",
        "ITERATE",
        "REJECT",
    ]
    for variant in variants:
        if variant in sec6_body.upper():
            return variant
    return None


def _parse_mutation_paths(sec7_body: str) -> list[str]:
    """Extract bullet-point mutation suggestions."""
    lines = sec7_body.splitlines()
    paths = []
    for line in lines:
        line = line.strip()
        # Accept lines starting with -, •, *, or numbered (1. 2.)
        if re.match(r"^[-•*]|^\d+\.", line):
            cleaned = re.sub(r"^[-•*\d.]\s*", "", line).strip()
            if cleaned:
                paths.append(cleaned)
    return paths


def _extract_family(rationale: str, sec6_body: str) -> Optional[str]:
    """
    Best-effort family extraction from rationale or decision context.
    Looks for known family names as substrings.
    """
    known_families = [
        "Momentum", "Value", "Quality", "Short-term Reversal",
        "Liquidity Pressure", "Volatility Compression", "Volume Anomaly",
        "Operating Efficiency", "Inventory & Cashflow Dynamics",
        "Behavioral Crowding", "Regime Shifts", "Dispersion Mechanics",
        "Residualized Industry Effects", "Microstructure Pressure",
        "Temporal Displacement",
    ]
    combined = rationale + " " + sec6_body
    for fam in known_families:
        if fam.lower() in combined.lower():
            return fam
    return None


def parse_alpha_output(raw: str) -> Optional[dict]:
    """
    Parse the full 8-field (v2) LLM alpha output into a structured dict.

    Returns:
        dict with keys: rationale, expression, metrics (dict),
        fingerprint (dict), ast_topology, ast_collision (list),
        refinement_log, decision, mutation_paths, simulation_payload,
        family — or None if parsing fails critically.
    """
    if not raw or not raw.strip():
        logger.warning("parse_alpha_output: received empty string")
        return None

    try:
        # v2 has 8 sections; [5]=AST, [6]=Refinement, [7]=Decision, [8]=Payload
        # v1 had 7 sections; [5]=Refinement, [6]=Decision, [7]=Mutation
        # Detect which format based on presence of 'AST TOPOLOGY HASH'
        is_v2 = "AST TOPOLOGY HASH" in raw.upper() or _section(raw, 5, 6).strip().startswith("Pattern")

        sec1 = _section(raw, 1, 2)
        sec2 = _section(raw, 2, 3)
        sec3 = _section(raw, 3, 4)
        sec4 = _section(raw, 4, 5)

        if is_v2:
            sec5_ast  = _section(raw, 5, 6)   # [5] AST TOPOLOGY HASH
            sec6      = _section(raw, 6, 7)   # [6] REFINEMENT LOG
            sec7_dec  = _section(raw, 7, 8)   # [7] DECISION
            sec8      = _section(raw, 8)      # [8] SIMULATION PAYLOAD
            refinement_log = sec6
            decision_src   = sec7_dec
            mutation_src   = ""  # v2 drops dedicated mutation section
        else:
            sec5_ast  = ""                    # not present in v1
            refinement_log = _section(raw, 5, 6)
            decision_src   = _section(raw, 6, 7)
            mutation_src   = _section(raw, 7)
            sec8           = ""

        expression = _extract_expression(sec2)
        if not expression:
            logger.warning("parse_alpha_output: could not extract expression from [2]")

        sharpe_min, sharpe_max = _parse_range(sec3, "Sharpe")
        fitness_min, fitness_max = _parse_range(sec3, "Fitness")
        turnover_min, turnover_max = _parse_range(sec3, r"Turnover")
        returns_pct = _parse_returns(sec3)  # v2 new field
        corr_risk = _parse_corr_risk(sec3)

        fingerprint = _parse_fingerprint(sec4)
        ast_topology, ast_collision = _parse_ast_topology(sec5_ast) if sec5_ast else (None, [])
        decision = _parse_decision(decision_src)
        simulation_payload = _parse_simulation_payload(sec8) if sec8 else None

        # If we can't get a decision at all, the LLM output is unusable
        if not decision:
            logger.warning(
                "parse_alpha_output: no decision found in decision section, raw snippet: %s",
                raw[-300:],
            )
            return None

        return {
            "rationale": sec1,
            "expression": expression or "",
            "metrics": {
                "sharpe_min": sharpe_min,
                "sharpe_max": sharpe_max,
                "fitness_min": fitness_min,
                "fitness_max": fitness_max,
                "turnover_min": turnover_min,
                "turnover_max": turnover_max,
                "returns_pct": returns_pct,  # v2
                "corr_risk": corr_risk,
            },
            "fingerprint": fingerprint,
            "ast_topology": ast_topology,      # v2
            "ast_collision": ast_collision,    # v2
            "refinement_log": refinement_log,
            "decision": decision,
            "mutation_paths": _parse_mutation_paths(mutation_src) if mutation_src else [],
            "simulation_payload": simulation_payload,  # v2
            "family": _extract_family(sec1, decision_src),
        }

    except Exception as exc:
        logger.error("parse_alpha_output: unexpected error — %s", exc, exc_info=True)
        return None
