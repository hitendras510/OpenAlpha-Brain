"""
OpenAlpha - Quant — IQC Constraint + Syntax Validator
Two public functions: validate_syntax() and validate_metrics().
Both return ValidationResult(passed, failures, warnings).
"""
from __future__ import annotations

import re
from typing import Optional

from models import ValidationResult

# ── Permitted operator whitelist ──────────────────────────────────────────────
PERMITTED_OPERATORS: set[str] = {
    "rank", "ts_rank", "ts_mean", "ts_std_dev", "ts_delta", "ts_zscore",
    "ts_decay_linear", "decay_linear", "group_neutralize", "abs", "log",
    "signed_power", "max", "min", "scale", "delay", "ts_sum", "ts_corr",
    "ts_regression", "ts_skewness", "ts_kurt", "ts_min", "ts_max",
    "ts_argmax", "ts_argmin", "ts_backfill", "vec_norm",
    "trade_when",  # v2: execution gating operator
    # arithmetic / field access not treated as operator calls
    "div", "mul", "add", "sub",
}

# Regex to find all function-call identifiers: word chars followed by (
_FUNC_CALL_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")

# Regex to detect float literals used as window arguments (after a comma)
# Matches patterns like: ts_mean(close, 20.5) → flags 20.5
_FLOAT_WINDOW_RE = re.compile(r",\s*(\d+\.\d+)\s*[,)]")

# Detect group_neutralize with correct second arg
_GN_RE = re.compile(
    r"group_neutralize\s*\(.*?,\s*(sector|industry|sub_industry|subindustry)\s*\)",
    re.IGNORECASE | re.DOTALL,
)

# ── Verified BRAIN FastExpr variable whitelist ────────────────────────────────
# ONLY these bare variable names are confirmed to exist in BRAIN FastExpr.
# Fundamental/Analyst data uses dataset-specific prefixed names (e.g. fn_sales_q)
# accessed via the BRAIN Data Explorer — NOT bare names like 'sales' or 'earnings'.
VALID_BRAIN_VARS: set[str] = {
    # Price / Volume (confirmed bare names)
    "open", "high", "low", "close", "vwap", "volume", "adv20", "returns", "cap",
    # Short Interest (confirmed bare names)
    "short_interest", "short_ratio", "days_to_cover",
    # Analyst (confirmed bare names)
    "analyst_rating", "price_target",
    # Neutralization args (identifiers, not data fields)
    "industry", "subindustry", "sector",
}

# Variables the LLM hallucinates — these DO NOT exist as bare names in BRAIN
# (fundamental/analyst data needs dataset-specific prefixes from Data Explorer)
KNOWN_INVALID_VARS: set[str] = {
    # Fundamental — require dataset prefix (e.g. fn_sales_q, fn_earnings_q)
    "sales", "earnings", "assets", "liabilities", "book", "cash_flow", "dividends",
    "revenue", "net_income", "gross_profit", "operating_income", "ebitda",
    "free_cash_flow", "debt", "equity", "book_value",
    # Financial ratios — not raw fields
    "pe_ratio", "pb_ratio", "ev", "roe", "roa", "roc",
    # Analyst — require dataset prefix
    "eps_estimate", "revenue_estimate", "rating_change", "analyst_consensus",
    "target_price", "recommendation",
    # Ownership — do not exist in BRAIN at all
    "institutional_ownership", "insider_ownership", "ownership_concentration",
    "float_shares", "shares_outstanding", "shares_float", "market_cap",
    # Other hallucinations
    "short_utilization",
}

# Regex to find bare variable identifiers (not followed by '(')
_VAR_RE = re.compile(r"\b([a-z][a-z0-9_]*)\b(?!\s*\()")


def _check_parens(expr: str) -> bool:
    """Stack-based parenthesis balance check. Returns True if balanced."""
    depth = 0
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False  # unmatched closing paren
    return depth == 0  # True only if every opener was closed


def validate_syntax(expression: str) -> ValidationResult:
    """
    Check BRAIN expression for structural correctness.

    Checks:
    1. Expression length: 5 ≤ len ≤ 2000
    2. group_neutralize(..., sector|industry) is present
    3. Parentheses are balanced (stack-based)
    4. All function calls use permitted operators only
    5. No float literals used as window arguments
    """
    failures: list[str] = []
    warnings: list[str] = []

    if not expression or not expression.strip():
        return ValidationResult(passed=False, failures=["Expression is empty"])

    expr = expression.strip()

    # 1. Length bounds
    if len(expr) < 5:
        failures.append(f"Expression too short ({len(expr)} chars, minimum 5)")
    if len(expr) > 2000:
        failures.append(f"Expression too long ({len(expr)} chars, maximum 2000)")

    # 2. group_neutralize presence and correct form
    if "group_neutralize" not in expr:
        failures.append("group_neutralize() is missing — required on every alpha")
    elif not _GN_RE.search(expr):
        warnings.append(
            "group_neutralize found but second arg is not 'sector' or 'industry'"
        )

    # 3. Balanced parentheses (stack-based)
    if not _check_parens(expr):
        failures.append("Unbalanced parentheses detected")

    # 4. Operator whitelist
    called_funcs = set(_FUNC_CALL_RE.findall(expr))
    # Filter out single-letter or data field names (e.g. no trailing paren normally)
    unknown = called_funcs - PERMITTED_OPERATORS
    if unknown:
        failures.append(f"Unknown/forbidden operators: {', '.join(sorted(unknown))}")

    # 5. Float window arguments (integers only allowed)
    float_windows = _FLOAT_WINDOW_RE.findall(expr)
    if float_windows:
        failures.append(
            f"Non-integer lookback window(s) detected: {float_windows} — "
            "all window arguments must be strict integers"
        )

    # 6. Invalid BRAIN variable check — catches hallucinated fields before API call
    identifiers = set(_VAR_RE.findall(expr.lower()))
    bad_vars = identifiers & KNOWN_INVALID_VARS
    if bad_vars:
        failures.append(
            f"INVALID BRAIN variables (will cause simulation ERROR): "
            f"{', '.join(sorted(bad_vars))}. "
            f"Use only: {', '.join(sorted(VALID_BRAIN_VARS - {'industry','subindustry','sector'}))}"
        )

    passed = len(failures) == 0
    return ValidationResult(passed=passed, failures=failures, warnings=warnings)



def validate_fitness(
    sharpe: float,
    returns_pct: float,
    turnover_pct: float,
) -> ValidationResult:
    """
    v2: Compute Fitness using the exact IQC formula.

    Formula: Fitness = Sharpe × sqrt(|Returns|) / max(Turnover, 0.125)
    where Returns and Turnover are decimal fractions (not percentages).

    Sweet spot: Sharpe ~1.4, Returns ~20%, Turnover ~20% → Fitness ~2.0
    """
    import math
    failures: list[str] = []
    warnings: list[str] = []

    returns_dec = abs(returns_pct) / 100.0
    turnover_dec = turnover_pct / 100.0
    turnover_denom = max(turnover_dec, 0.125)  # floor at 12.5%

    fitness = sharpe * math.sqrt(returns_dec) / turnover_denom
    breakdown = (
        f"Fitness = {sharpe} × sqrt({returns_pct}%={returns_dec:.4f}) "
        f"/ max({turnover_pct}%={turnover_dec:.4f}, 0.125) "
        f"= {sharpe} × {math.sqrt(returns_dec):.4f} / {turnover_denom:.4f} "
        f"= {fitness:.4f}"
    )

    if fitness <= 1.0:
        failures.append(
            f"Fitness {fitness:.4f} ≤ 1.0 — gate FAIL. {breakdown}"
        )
    elif fitness < 1.5:
        warnings.append(f"Fitness {fitness:.4f} is below the 1.5 competitive threshold.")

    passed = len(failures) == 0
    result = ValidationResult(passed=passed, failures=failures, warnings=warnings)
    result.fitness_computed = round(fitness, 4)
    result.fitness_breakdown = breakdown
    return result


def validate_metrics(parsed: dict) -> ValidationResult:
    """
    Check parsed IQC metric estimates against hard submission gates.

    Gates:
    - Sharpe ≥ 1.25  (uses sharpe_min as the conservative bound)
    - Fitness > 1.0  (v2: computed via exact formula when returns_pct available;
                          falls back to fitness_min from LLM estimate)
    - Turnover 1–70% (uses turnover_min ≥ 1, turnover_max ≤ 70)
    - Corr Risk != HIGH

    Returns ValidationResult with any failing gates listed.
    """
    import math
    failures: list[str] = []
    warnings: list[str] = []
    values: dict = {}

    metrics = parsed.get("metrics", {})

    sharpe_min: Optional[float] = metrics.get("sharpe_min")
    sharpe_max: Optional[float] = metrics.get("sharpe_max")
    fitness_min: Optional[float] = metrics.get("fitness_min")
    turnover_min: Optional[float] = metrics.get("turnover_min")
    turnover_max: Optional[float] = metrics.get("turnover_max")
    returns_pct: Optional[float] = metrics.get("returns_pct")
    corr_risk: Optional[str] = metrics.get("corr_risk")

    fitness_computed: Optional[float] = None
    fitness_breakdown: Optional[str] = None

    # Sharpe gate ≥ 1.25
    if sharpe_min is None:
        warnings.append("Sharpe estimate missing from LLM output")
    else:
        values["sharpe"] = sharpe_min
        if sharpe_min < 1.25:
            failures.append(
                f"Sharpe {sharpe_min} < 1.25 — gate FAIL (need ≥ 1.25)"
            )
        elif sharpe_min < 1.35:
            warnings.append(f"Sharpe {sharpe_min} is marginal — consider pushing above 1.35")

    # Turnover gate 1–70% (needed for fitness formula too)
    if turnover_min is None and turnover_max is None:
        warnings.append("Turnover estimate missing from LLM output")
    else:
        lo = turnover_min or 0.0
        hi = turnover_max or turnover_min or 0.0
        values["turnover_range"] = f"{lo}%–{hi}%"
        if lo < 1.0:
            failures.append(
                f"Turnover lower bound {lo}% < 1% — gate FAIL (need 1–70%)"
            )
        if hi > 70.0:
            failures.append(
                f"Turnover upper bound {hi}% > 70% — gate FAIL (need 1–70%)"
            )

    # Fitness gate: v2 uses exact formula when all inputs are available
    turnover_for_formula = ((turnover_min or 0) + (turnover_max or turnover_min or 0)) / 2
    if sharpe_min is not None and returns_pct is not None and turnover_for_formula > 0:
        # Use exact formula (v2 path)
        fit_result = validate_fitness(sharpe_min, returns_pct, turnover_for_formula)
        fitness_computed = fit_result.fitness_computed
        fitness_breakdown = fit_result.fitness_breakdown
        failures.extend(fit_result.failures)
        warnings.extend(fit_result.warnings)
    elif fitness_min is not None:
        # Fallback: use LLM-estimated fitness (v1 path)
        values["fitness"] = fitness_min
        if fitness_min <= 1.0:
            failures.append(
                f"Fitness {fitness_min} ≤ 1.0 — gate FAIL (need > 1.0) [LLM estimate]"
            )
    else:
        warnings.append(
            "Fitness cannot be computed (missing Sharpe, Returns, or Turnover) — "
            "and no LLM fitness estimate provided"
        )

    # Corr Risk — HIGH triggers re-iteration
    if corr_risk == "HIGH":
        failures.append(
            "Corr Risk is HIGH — alpha too similar to known factor families"
        )
    elif corr_risk is None:
        warnings.append("Corr Risk field missing")

    passed = len(failures) == 0
    result = ValidationResult(passed=passed, failures=failures, warnings=warnings)
    result.fitness_computed = fitness_computed
    result.fitness_breakdown = fitness_breakdown
    return result


def fingerprint_collision(new_fp: dict, existing_fps: list[dict]) -> bool:
    """
    Return True if new_fp shares ≥ 2 fields with any fingerprint in existing_fps.
    None values are ignored (partial fingerprints treated charitably).
    """
    keys = ["dataset", "topology", "temporal", "normalization", "direction", "neutral"]
    for fp in existing_fps:
        matches = sum(
            1 for k in keys
            if new_fp.get(k) and fp.get(k)
            and new_fp[k].lower() == fp[k].lower()
        )
        if matches >= 2:
            return True
    return False
