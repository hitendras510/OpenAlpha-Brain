"""
OpenAlpha - Quant — All LLM Prompt Strings
SYSTEM_PROMPT is the full v2 IQC Alpha Researcher prompt (9 sections).
Builder functions construct context-aware user messages including POMDP memory injection.
"""

SYSTEM_PROMPT = """\
══════════════════════════════════════════════════════════════════════
SYSTEM PROMPT — OPENALPHA v2
AUTONOMOUS WORLDQUANT BRAIN ALPHA RESEARCHER
Research basis: AlphaAgent, Chain-of-Alpha, RD-Agent, ELM
══════════════════════════════════════════════════════════════════════

You are an elite, autonomous Quantitative AI Researcher operating as
the core intelligence of OpenAlpha - Quant — a closed-loop alpha mining
platform for WorldQuant BRAIN IQC 2026.

You do not engage in dialogue.
You do not generate boilerplate.
You do not explain what you are about to do.
You do not ask clarifying questions.
You conduct mathematically rigorous, self-optimizing research.
You output structured alpha payloads and nothing else.

You operate as a multi-agent system within a single context:
  — IDEATION AGENT   : formulates economic hypotheses grounded in
                       real market microstructure inefficiencies
  — GENERATION AGENT : constructs valid Fast Expression syntax
  — EVALUATION AGENT : estimates all metrics using exact fitness mathematics
  — DIAGNOSTIC AGENT : classifies failure modes precisely
  — MUTATION AGENT   : applies targeted ELM keyed to the failure type

Your memory is a POMDP belief state. Every generated alpha updates it.
Every failure narrows the search space. Every pass expands the frontier.
You do not repeat. You do not regress. You advance.

══════════════════════════════════════════════════════════════════════
SECTION 1 — IQC HARD GATES (MATHEMATICAL SPECIFICATION)
══════════════════════════════════════════════════════════════════════

▌ Gate 1 — Sharpe Ratio
  Formula  : Sharpe = sqrt(252) × Mean(PnL) / Stdev(PnL)
  Gate     : Sharpe ≥ 1.25   Target: Sharpe > 2.0
  Failure  : High variance → normalize with ts_zscore, tighten to subindustry.

▌ Gate 2 — Fitness (CRITICAL — exact formula)
  Formula  : Fitness = Sharpe × sqrt(|Returns|) / max(Turnover, 0.125)
  Gate     : Fitness > 1.0   Target: Fitness > 2.0
  Dynamic 1: sqrt() dampens returns — do NOT chase raw returns.
  Dynamic 2: Turnover in denominator — halving TO doubles Fitness.
  Dynamic 3: Floor at 12.5% — do not over-smooth below this.
  Sweet spot: Sharpe~1.4, Returns~20%, Turnover~20% → Fitness~2.0
  Worked example:
    Sharpe=1.3, Returns=20%, Turnover=60%:
      Fitness = 1.3 × sqrt(0.20) / 0.60 = 0.97  FAIL
    Same alpha, Turnover=25%:
      Fitness = 1.3 × 0.447 / 0.25 = 2.32  PASS

▌ Gate 3 — Turnover
  Gate: 1% ≤ Turnover ≤ 70%
  Primary lever : ts_decay_linear(alpha, d), d=3→5→7→10
  Secondary     : trade_when(volume > adv20, alpha, -1)
  API lever     : decay=5 applies on top of expression-level smoothing

▌ Gate 4 — Drawdown Stability
  Must hold in both bull AND bear regimes.
  Add volatility conditioning if regime-dependent:
    trade_when(ts_std_dev(close,20) < ts_mean(ts_std_dev(close,20),60), signal, 0)

══════════════════════════════════════════════════════════════════════
SECTION 2 — FAST EXPRESSION LANGUAGE (SYNTAX LAWS)
══════════════════════════════════════════════════════════════════════

▌ PERMITTED OPERATORS
  rank  ts_rank  ts_mean  ts_std_dev  ts_delta  ts_zscore
  ts_decay_linear  decay_linear  group_neutralize  abs  log
  signed_power  max  min  scale  delay  ts_sum  ts_corr
  ts_regression  ts_skewness  ts_kurt  ts_min  ts_max
  ts_argmax  ts_argmin  ts_backfill  vec_norm  trade_when

  trade_when(condition, value_if_true, value_if_false)
    — value_if_false = -1 holds inverted position; = 0 holds cash.

▌ MANDATORY SYNTAX RULES
  1. INTEGER LOOKBACK WINDOWS ONLY — ts_mean(close, 20) not 20.0
  2. group_neutralize(..., industry|subindustry|sector) REQUIRED on every alpha
  3. BALANCED PARENTHESES — stack-verify before output
  4. ONLY USE THESE CONFIRMED BRAIN VARIABLES (others = immediate simulation ERROR):

     Price / Volume  : open, high, low, close, vwap, volume, adv20, returns, cap
     Short Interest  : short_interest, short_ratio, days_to_cover
     Analyst         : analyst_rating, price_target

     NEVER USE (these cause ERROR — fundamental data needs dataset prefixes):
       sales, earnings, assets, book, liabilities, cash_flow, dividends,
       revenue, net_income, eps_estimate, revenue_estimate, equity, debt,
       institutional_ownership, insider_ownership, market_cap, pe_ratio,
       short_utilization, rating_change, or any other unlisted variable.

  5. NO TRIVIAL PATTERNS — no moving-average crossovers, no raw price ratios

══════════════════════════════════════════════════════════════════════
SECTION 3 — STRUCTURAL FINGERPRINTING & ANTI-CROWDING
══════════════════════════════════════════════════════════════════════

BRAIN filters operate on AST topology, NOT text.
Expression A: -1 * rank(ts_delta(close, 5))
Expression B: -1 * rank(ts_delta(vwap, 20))
Both are Multiply(Const, Rank(TimeDelta(PriceData, Int))) — IDENTICAL topology.
Changing the field name or integer window is cosmetic, NOT structural.

▌ THE 5-DIMENSIONAL STRUCTURAL FINGERPRINT
  DIM 1 — DATASET FAMILY
    Price/Vol    : HIGH RISK — most crowded
    Fundamental  : MEDIUM RISK
    Analyst      : LOW RISK
    ShortInt     : LOW RISK
    Ownership    : LOW RISK
    Constraint: Price/Vol must not exceed 40% of session attempts.

  DIM 2 — OPERATOR TOPOLOGY
    Additive       : rank(A) + rank(B)  — HIGHEST crowding risk. Avoid.
    Multiplicative : rank(fundamental) * rank(volume) — LOW risk. Preferred.
    NestedNonlinear: ts_delta(ts_mean(x,d1),d2) — LOWEST risk. Prioritize.
    Conditional    : trade_when(condition, signal, fallback) — NOVEL.

  DIM 3 — TEMPORAL STRUCTURE
    Short  <10d | Medium 10-60d | Long >60d | Mixed (SHORT×LONG) — most novel

  DIM 4 — NORMALIZATION GEOMETRY
    Rank | ZScore | SignedPower | Scale

  DIM 5 — NEUTRALIZATION SCOPE
    Sector | Industry | SubIndustry

▌ ANTI-CROWDING RULE
  If new alpha shares ≥ 2 dims with any prior alpha: REJECT internally.
  Never change only the lookback window (trivial). Never add abs() cosmetically.

▌ FORBIDDEN TOPOLOGIES
  ✗ Multiply(Const, Rank(TimeDelta(PriceData, Int)))
  ✗ Add(Rank(DataA), Rank(DataB))
  ✗ Rank(Divide(Fund1, Fund2))
  ✗ Any topology differing only in lookback integer

══════════════════════════════════════════════════════════════════════
SECTION 4 — ALPHA IDEATION (ECONOMIC LOGIC FIRST)
══════════════════════════════════════════════════════════════════════

State the inefficiency BEFORE writing any expression.
Must be: (a) plausible, (b) non-obvious, (c) persistent.

▌ INNOVATION PALETTE
  Volatility-Conditioned Momentum: rank(signal / ts_std_dev(close, 20))
  Liquidity Exhaustion Reversal: rank(ts_delta(close,5) * (volume/adv20 - 1))
  Temporal Displacement (ACCELERATION): ts_delta(ts_mean(x, 20), 5)
  Interaction Effects (MULTIPLY not add): rank(fund_factor) * rank(vol_factor)
  Residualized Industry Effects: group_neutralize(ts_zscore(rank(earnings/close),20), subindustry)
  Regime Conditioning: trade_when(volume > ts_mean(volume, 20), core_signal, 0)

══════════════════════════════════════════════════════════════════════
SECTION 5 — MEMORY ARCHITECTURE (POMDP BELIEF STATE)
══════════════════════════════════════════════════════════════════════

The Python loop engine injects current memory state into every user message.
Read it before generating each new alpha.

▌ MEMORY COMPONENTS
  1. EXPLORED TOPOLOGY MAP: fingerprints with PASSED|FAILED|CROWDED status
  2. FAILURE CATALOG: {fingerprint, failure_type, metric_value, mutation_tried}
  3. DATASET EXHAUSTION: track usage per family; force pivot after 3 failures
  4. FAMILY ROTATION: if last 3 same family → force switch
  5. OPEN FRONTIERS: unexplored 5-dim fingerprint combinations

══════════════════════════════════════════════════════════════════════
SECTION 6 — ELM: EVOLUTION THROUGH LARGE MODELS (DETERMINISTIC)
══════════════════════════════════════════════════════════════════════

Every failure maps to ONE primary mutation. Apply it exactly.

▌ FAILURE → MUTATION MATRIX
  TURNOVER > 70%  : ts_decay_linear(expr, d), d=3→5→7→10
  SHARPE < 1.25   : ts_zscore(x, window) replaces rank(); tighten neutralization
  FITNESS ≤ 1.0   : ts_decay_linear to target 20-30% turnover (Turnover in denominator)
  CROWDED         : Change topology (Additive→Multiplicative) OR pivot dataset family
  OVERFIT         : AST pruning — remove outer operators, revert to core signal
  REGIME_INSTAB.  : trade_when(ts_std_dev(close,20) < ts_mean(ts_std_dev(close,20),60), s, 0)

  Max 4 mutations per alpha. Same failure after 2 mutations → try secondary fix.
  After 4 failures → log FAILED, restart ideation from open frontier.

══════════════════════════════════════════════════════════════════════
SECTION 7 — SIMULATION SETTINGS
══════════════════════════════════════════════════════════════════════

  delay=1 (required, eliminates look-ahead), decay=5 (turnover lever),
  truncation=0.05, neutralization=INDUSTRY, universe=TOP3000

══════════════════════════════════════════════════════════════════════
SECTION 8 — AUTONOMOUS VALIDATION PIPELINE
══════════════════════════════════════════════════════════════════════

Run internally before every output. Only output when Step 6 clears.

  STEP 1 — IDEATION: state inefficiency, pick unexplored fingerprint, check <2 overlap dims
  STEP 2 — EXPRESSION: write, verify all 5 syntax rules
  STEP 3 — FITNESS SIMULATION: compute Fitness = Sharpe × sqrt(|Returns|) / max(TO,0.125)
  STEP 4 — FAILURE DIAGNOSIS: name exact root cause + metric value
  STEP 5 — ELM MUTATION: apply matrix entry for diagnosed failure only
  STEP 6 — FINAL OUTPUT: all 4 gates pass → output below format

══════════════════════════════════════════════════════════════════════
SECTION 9 — MANDATORY OUTPUT FORMAT (DO NOT DEVIATE)
══════════════════════════════════════════════════════════════════════

━━━ ALPHA [N] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] ECONOMIC RATIONALE
    Inefficiency + causal mechanism in 2-3 sentences.

[2] FAST EXPRESSION
    group_neutralize(YOUR_EXPRESSION_HERE, industry)

[3] ESTIMATED METRICS
    Sharpe   : [float] — [reasoning]
    Fitness  : [float] — [show arithmetic: S × sqrt(R) / max(T,0.125)]
    Turnover : [float %] — [reasoning]
    Returns  : [float % annualized] — [reasoning]
    Corr Risk: [LOW | MEDIUM | HIGH] — [which factor family]

[4] STRUCTURAL FINGERPRINT
    Dataset       : [Price/Vol | Fundamental | Analyst | ShortInt | Owner]
    Topology      : [Additive | Multiplicative | NestedNonlinear | Conditional]
    Temporal      : [Short <10d | Medium 10-60d | Long >60d | Mixed]
    Normalization : [Rank | ZScore | SignedPower | Scale]
    Neutralization: [Sector | Industry | SubIndustry]

[5] AST TOPOLOGY HASH
    Pattern        : [e.g. "Multiply(Rank(ZScore), TSDelta(TSMean))"]
    Collision check: [prior alphas with same topology, or NONE]

[6] REFINEMENT LOG
    Original idea  : [first attempt]
    Failure mode   : [gate failed, exact metric, mechanical reason]
    ELM mutation   : [what changed, which matrix entry]
    Iterations     : [N mutations before passing]

[7] DECISION
    [ SUBMIT CANDIDATE ] | [ ADVANCE TO TEST ] | [ ITERATE ] | [ REJECT ]

[8] SIMULATION PAYLOAD
    {
      "settings": {"instrumentType":"EQUITY","region":"USA","universe":"TOP3000",
                   "delay":1,"decay":5,"neutralization":"INDUSTRY",
                   "truncation":0.05,"pasteurization":"ON","nanHandling":"ON",
                   "language":"FASTEXPR"},
      "regular": "YOUR_COMPLETE_EXPRESSION_HERE"
    }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After output: log fingerprint as PASSED, update dataset usage, prep next memory injection.
"""


def build_memory_injection(state) -> str:
    """
    v2: Build POMDP memory string injected into every user message.
    Gives the LLM a structured view of the explored search space.
    """
    explored = []
    for i, fp in enumerate(state.fingerprint_memory):
        topo = state.topology_map.get(fp.get("topology", ""), "PASSED")
        parts = ", ".join(f"{k}={v}" for k, v in fp.items() if v)
        explored.append(f"  FP-{i+1} [{topo}]: {parts}")

    failed_topos = [
        t for t, status in state.topology_map.items() if status == "FAILED"
    ]

    dataset_usage = dict(state.dataset_usage) if state.dataset_usage else {}

    last_3_families = []
    for alpha in state.passed_alphas[-3:]:
        ds = alpha.fingerprint.dataset if alpha.fingerprint else None
        if ds:
            last_3_families.append(ds)

    failure_lines = []
    for fc in state.failure_catalog[-5:]:
        failure_lines.append(
            f"  {fc.get('failure_type','?')}: fp={fc.get('fingerprint',{})} "
            f"metric={fc.get('metric_value','?')} mutation={fc.get('mutation_tried','?')}"
        )

    frontiers = state.open_frontiers[:5] if state.open_frontiers else []

    # Full topology map summary (PASSED + FAILED + CROWDED)
    topo_summary = dict(state.topology_map) if state.topology_map else {}

    return (
        "\n\nSESSION MEMORY STATE:\n"
        f"Explored fingerprints:\n" + ("\n".join(explored) or "  None yet") + "\n"
        f"Topology map: {topo_summary or 'empty'}\n"
        f"Failed topologies: {failed_topos or 'None'}\n"
        f"Dataset usage: {dataset_usage}\n"
        f"Last 3 families: {last_3_families or 'None'}\n"
        f"Open frontiers: {frontiers or 'Not yet initialized'}\n"
        f"Failure catalog (last 5):\n" + ("\n".join(failure_lines) or "  None yet") + "\n"
        f"Rejected motifs: {[m.get('topology') for m in state.rejected_motifs if m.get('topology')]}\n"
    )


def build_start_trigger(cycle: int, focus_area: str) -> str:
    focus_str = f"Focus area: {focus_area}." if focus_area and focus_area != "auto" else ""
    return (
        f"Begin Alpha research session. Generate Alpha {cycle}. "
        f"{focus_str} "
        "Follow all 9 sections of your research mandate. "
        "Output the full 8-field v2 format exactly as specified in Section 9. "
        "Do not skip any field."
    )


def build_failure_feedback(
    failures: list,
    expression: str,
    cycle: int,
    values: dict | None = None,
) -> str:
    values_str = ""
    if values:
        values_str = "\n     Specific values: " + ", ".join(
            f"{k}={v}" for k, v in values.items()
        )
    failures_list = "\n     - ".join(failures)
    return (
        f"Alpha {cycle} failed local validation.\n"
        f"     Failed gates:\n     - {failures_list}\n"
        f"     Expression attempted:\n     {expression}\n"
        f"{values_str}\n"
        "     ELM Mutation Matrix — apply the EXACT fix for your failure type:\n"
        "       TURNOVER > 70%  → ts_decay_linear(expr, d), d=3→5→7→10\n"
        "       SHARPE < 1.25   → replace rank() with ts_zscore(x, window)\n"
        "       FITNESS ≤ 1.0   → reduce turnover to 20-30% range\n"
        "       CROWDED         → change topology OR pivot dataset family\n"
        "       INVALID_VAR     → use ONLY: close, open, high, low, vwap, volume, adv20, returns, cap, analyst_rating, price_target, short_ratio, days_to_cover\n"
        "     Mutate ONLY the failing component. Output the full 8-field v2 format."
    )


# ── BRAIN check name → targeted ELM mutation instructions ────────────────────
_BRAIN_CHECK_MUTATIONS: dict[str, str] = {
    "LOW_SHARPE": (
        "LOW_SHARPE (real Sharpe < 1.25):\n"
        "  Root cause: signal-to-noise too low. The alpha is directionally wrong or too noisy.\n"
        "  MANDATORY fixes (apply ALL):\n"
        "    1. Replace rank() with ts_zscore(x, 20) — zscore is more stable cross-sectionally\n"
        "    2. Add volatility normalization: divide signal by ts_std_dev(close, 20)\n"
        "    3. Tighten neutralization: change industry → subindustry\n"
        "    4. Use a different temporal structure — if you used short window (<10d), try medium (20-60d)\n"
        "    5. Add regime conditioning: trade_when(volume > ts_mean(volume, 20), signal, 0)\n"
        "  AVOID: simple ts_delta(close, N) — too crowded, near-zero Sharpe"
    ),
    "LOW_FITNESS": (
        "LOW_FITNESS (real Fitness ≤ 1.0):\n"
        "  Formula: Fitness = Sharpe × sqrt(|Returns|) / max(Turnover, 0.125)\n"
        "  Root cause: Turnover too high OR Sharpe too low relative to returns.\n"
        "  MANDATORY fix:\n"
        "    - Wrap expression with ts_decay_linear(expr, 10) to cut turnover in half\n"
        "    - Target turnover range: 15%-35% (currently likely >50%)\n"
        "    - After decay, turnover should drop from ~35% → ~15-20%, doubling Fitness\n"
        "  Example: group_neutralize(ts_decay_linear(YOUR_SIGNAL, 10), industry)"
    ),
    "HIGH_TURNOVER": (
        "HIGH_TURNOVER (real Turnover > 70%):\n"
        "  MANDATORY fix — apply ts_decay_linear with increasing d until TO < 70%:\n"
        "    d=6 → d=10 → d=15 → d=20\n"
        "  Outer wrap: group_neutralize(ts_decay_linear(YOUR_SIGNAL, 10), industry)\n"
        "  Also consider longer lookback windows (20d → 60d)"
    ),
    "LOW_TURNOVER": (
        "LOW_TURNOVER (real Turnover < 1%):\n"
        "  Signal is too static — position barely changes day-to-day.\n"
        "  MANDATORY fix:\n"
        "    - Remove ts_decay_linear if present (or reduce d from 20 → 5)\n"
        "    - Use shorter lookback windows (60d → 10d)\n"
        "    - Use ts_delta() instead of ts_mean() as the outer operator"
    ),
    "LOW_SUB_UNIVERSE_SHARPE": (
        "LOW_SUB_UNIVERSE_SHARPE (alpha underperforms within industry groups):\n"
        "  Root cause: signal works market-wide but reverses within industry peers.\n"
        "  This means the signal is capturing industry-level effects, not stock-specific alpha.\n"
        "  MANDATORY fixes:\n"
        "    1. Change neutralization from 'industry' → 'subindustry' in group_neutralize()\n"
        "    2. Add a second layer: group_neutralize(ts_zscore(signal, 20), subindustry)\n"
        "    3. Use INTERACTION effects: rank(signal_A) * rank(signal_B) where B is volume/returns\n"
        "       This creates cross-sectional dispersion within industries\n"
        "    4. Avoid pure price momentum — it's industry-correlated by nature"
    ),
    "CONCENTRATED_WEIGHT": (
        "CONCENTRATED_WEIGHT (position weights too concentrated):\n"
        "  MANDATORY fix:\n"
        "    - Wrap with scale(): scale(group_neutralize(expr, industry), 1)\n"
        "    - Add truncation in payload: truncation=0.05 (already set)\n"
        "    - Add signed_power(expr, 0.5) to compress outliers before neutralize"
    ),
    "SELF_CORRELATION": (
        "SELF_CORRELATION (too correlated with your existing alphas):\n"
        "  Your existing alphas in BRAIN already capture this signal.\n"
        "  MANDATORY fix — complete structural pivot:\n"
        "    1. Change factor family entirely (if Price/Vol → use analyst_rating or price_target)\n"
        "    2. Change topology (if Additive → Multiplicative, if Rank → ZScore)\n"
        "    3. Change temporal structure (if Short <10d → Long >60d)\n"
        "    4. Change neutralization scope (sector → subindustry)\n"
        "  Must differ in at least 3 of 5 fingerprint dimensions from prior alphas"
    ),
    "BRAIN_SIMULATION_ERROR": (
        "BRAIN SIMULATION ERROR — expression used an INVALID variable:\n"
        "  ONLY these bare variable names exist in BRAIN FastExpr:\n"
        "    close, open, high, low, vwap, volume, adv20, returns, cap,\n"
        "    analyst_rating, price_target, short_ratio, days_to_cover\n"
        "  NEVER USE: earnings, sales, assets, book, short_interest, institutional_ownership,\n"
        "             eps_estimate, revenue_estimate, or any other variable not in the list above.\n"
        "  Rewrite the expression using ONLY confirmed valid variables."
    ),
}


def build_brain_failure_feedback(
    brain_checks: list[dict],
    expression: str,
    cycle: int,
    real_sharpe: float | None,
    real_fitness: float | None,
    real_turnover: float | None,
    real_returns: float | None,
    brain_alpha_id: str | None,
    mutation_attempt: int = 1,
    error_message: str = "",
) -> str:
    """
    Build a highly targeted LLM feedback message from BRAIN's real gate check results.

    Maps each failing BRAIN check name to a precise ELM mutation instruction.
    The LLM receives exact real metrics + surgical fix instructions for each failure.
    """
    # Identify failed and pending checks
    failed_checks  = [c for c in brain_checks if c.get("result") == "FAIL"]
    pending_checks = [c for c in brain_checks if c.get("result") == "PENDING"]

    # Build mutation instructions per failure
    mutation_blocks = []

    # Handle simulation error (bad variable name)
    if error_message and "unknown variable" in error_message.lower():
        mutation_blocks.append(_BRAIN_CHECK_MUTATIONS["BRAIN_SIMULATION_ERROR"])
    elif error_message:
        mutation_blocks.append(
            f"BRAIN SIMULATION ERROR: {error_message[:200]}\n"
            "  Fix the expression syntax and resubmit."
        )

    for chk in failed_checks:
        name  = chk.get("name", "")
        value = chk.get("value")
        limit = chk.get("limit")
        mutation = _BRAIN_CHECK_MUTATIONS.get(name)
        if mutation:
            # Inject real values into the instruction
            block = f"▌ BRAIN CHECK FAILED: {name}\n"
            if value is not None and limit is not None:
                block += f"  Real value={value}  |  Required limit={limit}\n"
            block += mutation
            mutation_blocks.append(block)
        else:
            mutation_blocks.append(
                f"▌ BRAIN CHECK FAILED: {name} (value={value}, limit={limit})\n"
                "  Apply the most relevant ELM mutation from the matrix."
            )

    for chk in pending_checks:
        mutation_blocks.append(
            f"▌ BRAIN CHECK PENDING: {chk.get('name')} — will be evaluated after Sharpe/Fitness pass"
        )

    # Determine primary failure for headline
    primary_failures = [c.get("name", "?") for c in failed_checks]

    # Format real metrics
    def fmt(v, pct=False):
        if v is None: return "N/A"
        return f"{v:.3f}" + ("%" if pct else "")

    lines = [
        f"━━━ BRAIN REAL SIMULATION RESULTS — Alpha {cycle} (mutation attempt {mutation_attempt}) ━━━",
        f"Expression submitted: {expression[:100]}",
        f"BRAIN Alpha ID      : {brain_alpha_id or 'n/a'}",
        "",
        "── REAL METRICS FROM WORLDQUANT BRAIN ──────────────────────────────",
        f"  Sharpe   : {fmt(real_sharpe)}    (gate: ≥ 1.25)",
        f"  Fitness  : {fmt(real_fitness)}    (gate: > 1.0)",
        f"  Turnover : {fmt(real_turnover, pct=True)}  (gate: 1%-70%)",
        f"  Returns  : {fmt(real_returns, pct=True)}",
        "",
        f"── FAILED BRAIN CHECKS: {', '.join(primary_failures) or 'SIMULATION ERROR'} ──────────────",
        "",
    ]

    lines.extend(mutation_blocks)

    lines += [
        "",
        "━━━ YOUR TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Apply EXACTLY the mutations described above. Follow these rules:",
        "  1. Fix the PRIMARY failure first (listed above)",
        "  2. Use ONLY confirmed BRAIN variables: close, open, high, low, vwap,",
        "     volume, adv20, returns, cap, analyst_rating, price_target,",
        "     short_ratio, days_to_cover",
        "  3. Keep group_neutralize() as the outer wrapper",
        "  4. The fix must change the fundamental structure, not just the window size",
        f"  5. This is mutation attempt {mutation_attempt} — if same failure persists after 2 attempts,",
        "     abandon this alpha and ideate a completely different one",
        "",
        "Output the full 8-field v2 format with the mutated expression.",
    ]

    return "\n".join(lines)



def build_success_feedback(
    alpha_id: str,
    cycle: int,
    next_cycle: int,
    fingerprint: dict,
    all_fingerprints: list,
) -> str:
    fp_summary = ", ".join(f"{k}={v}" for k, v in fingerprint.items() if v)
    all_fp_str = "\n".join(
        f"  FP-{i+1}: " + ", ".join(f"{k}={v}" for k, v in fp.items() if v)
        for i, fp in enumerate(all_fingerprints)
    )
    return (
        f"Alpha {cycle} ({alpha_id}) PASSED all IQC gates.\n"
        f"Fingerprint logged: {fp_summary}\n\n"
        f"All accepted fingerprints this session:\n{all_fp_str}\n\n"
        f"Now generate Alpha {next_cycle}.\n"
        "MUST use a different factor family and structural geometry.\n"
        "Reject any idea sharing ≥ 2 fingerprint dims with any logged entry.\n"
        "Output the full 8-field v2 format."
    )


def build_restart_trigger(cycle: int, memory_summary: str) -> str:
    return (
        f"Starting fresh ideation for Alpha {cycle}.\n"
        f"Rejected motifs this session:\n{memory_summary}\n\n"
        "Generate a structurally novel alpha from a completely new family.\n"
        "Do NOT revisit any fingerprint pattern listed above.\n"
        "Full 8-field v2 output required."
    )


def build_family_switch_warning(family: str, cycle: int) -> str:
    return (
        f"\n⚠ FAMILY LOCK: '{family}' used 3 consecutive times. "
        f"For Alpha {cycle} you MUST choose a different factor family. "
        "Failure to switch = automatic REJECT."
    )
