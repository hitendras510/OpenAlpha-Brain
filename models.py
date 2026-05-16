"""
OpenAlpha - Quant — Pydantic Data Models
Single source of truth for all data shapes used across the system.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    IDLE = "IDLE"
    GENERATING = "GENERATING"
    PARSING = "PARSING"
    VALIDATING = "VALIDATING"
    ITERATING = "ITERATING"
    SUBMITTING = "SUBMITTING"   # v2: waiting for BRAIN simulation
    PASS = "PASS"
    FAIL = "FAIL"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class BrainSimStatus(str, Enum):
    PENDING  = "PENDING"
    RUNNING  = "RUNNING"
    PASS     = "PASS"
    FAIL     = "FAIL"
    ERROR    = "ERROR"
    SKIPPED  = "SKIPPED"   # no BRAIN credentials configured


class BrainSubmissionResult(BaseModel):
    """Result from submitting an alpha to WorldQuant BRAIN API."""
    status: BrainSimStatus = BrainSimStatus.PENDING
    alpha_id: Optional[str] = None       # BRAIN-assigned alpha ID
    real_sharpe: Optional[float] = None
    real_fitness: Optional[float] = None
    real_turnover: Optional[float] = None
    real_returns: Optional[float] = None
    real_drawdown: Optional[float] = None
    gate_failures: List[str] = []
    gate_warnings: List[str] = []
    error_message: Optional[str] = None
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AlphaMetrics(BaseModel):
    """Estimated metrics extracted from the LLM's [3] ESTIMATED METRICS section."""
    sharpe_min: Optional[float] = None
    sharpe_max: Optional[float] = None
    fitness_min: Optional[float] = None
    fitness_max: Optional[float] = None
    fitness_computed: Optional[float] = None     # v2: computed via exact formula
    fitness_breakdown: Optional[str] = None      # v2: shows arithmetic
    turnover_min: Optional[float] = None
    turnover_max: Optional[float] = None
    returns_pct: Optional[float] = None          # v2: annualized returns estimate
    corr_risk: Optional[str] = None  # LOW | MEDIUM | HIGH


class AlphaFingerprint(BaseModel):
    """6-field structural fingerprint for anti-crowding memory."""
    dataset: Optional[str] = None       # fundamental | price_volume | analyst | ...
    topology: Optional[str] = None      # additive | multiplicative | nonlinear
    temporal: Optional[str] = None      # short | medium | long
    normalization: Optional[str] = None # rank | zscore | scale | signed_power
    direction: Optional[str] = None     # mean-reverting | trending | regime-switching
    neutral: Optional[str] = None       # sector | industry


class AlphaResult(BaseModel):
    """A single fully-parsed alpha that survived the validation pipeline."""
    alpha_id: str
    family: Optional[str] = None
    expression: str
    rationale: str
    metrics: AlphaMetrics
    fingerprint: AlphaFingerprint
    decision: str
    refinement_log: Optional[str] = None
    mutation_paths: List[str] = []
    # v2 fields
    ast_topology: Optional[str] = None
    ast_collision: List[str] = []
    simulation_payload: Optional[dict] = None
    # BRAIN submission result
    brain: Optional[BrainSubmissionResult] = None
    cycle_num: int
    passed: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionState(BaseModel):
    """Full session state — serialised to / deserialised from sessions/{id}.json."""
    id: str
    status: SessionStatus = SessionStatus.IDLE
    cycle: int = 0
    focus_area: str = ""
    passed_alphas: List[AlphaResult] = []
    fingerprint_memory: List[dict] = []    # raw dicts for JSON round-trip simplicity
    family_run_tracker: List[str] = []     # last N families generated
    rejected_motifs: List[dict] = []       # fingerprints that caused REJECT
    conversation_history: List[dict] = []  # [{role, content}] for LLM context
    mutation_count: int = 0                # mutations on the current alpha
    stop_requested: bool = False
    last_decision: Optional[str] = None
    consecutive_same_decision: int = 0
    error_message: Optional[str] = None
    # v2 POMDP belief-state components
    topology_map: dict = {}               # {topology_hash: "PASSED"|"FAILED"|"CROWDED"}
    dataset_usage: dict = {}              # {family_name: count}
    failure_catalog: List[dict] = []      # [{fingerprint, failure_type, mutation_tried}]
    open_frontiers: List[dict] = []       # unexplored 5-dim fingerprint combos
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StartSessionRequest(BaseModel):
    focus_area: str = "auto"


class ValidationResult(BaseModel):
    """Returned by every validator function."""
    passed: bool
    failures: List[str] = []
    warnings: List[str] = []
    # v2: exact fitness formula result
    fitness_computed: Optional[float] = None
    fitness_breakdown: Optional[str] = None
