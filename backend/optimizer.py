"""
optimizer.py
Orchestrates the full optimization pipeline for Phase 3.

Pipeline:
  1. Translate NL -> original SQL (LLM call 1)
  2. Run EXPLAIN ANALYZE on original SQL
  3. Parse plan + detect anti-patterns
  4. Build optimization prompt with anti-patterns + plan summary
  5. Rewrite SQL (LLM call 2)
  6. Run EXPLAIN ANALYZE on rewritten SQL
  7. Compute before/after cost + time delta
  8. Return full comparison result
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional

from schema_introspector import get_schema_info
from prompt_builder import build_translation_prompt, build_optimization_prompt
from llm_client import call_llm, LLMResult
from sql_runner import run_explain, SQLExecutionError
from plan_parser import parse_explain_output, summarize_plan, ParsedPlan
from antipattern_detector import detect_antipatterns, AntiPattern

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class PlanMetrics:
    execution_time_ms: float
    planning_time_ms: float
    total_cost: float
    node_types: list[str]


@dataclass
class OptimizationResult:
    # Natural language input
    nl_query: str

    # Original SQL + metrics
    original_sql: str
    original_plan: PlanMetrics
    antipatterns: list[AntiPattern]

    # Rewritten SQL + metrics
    optimized_sql: str
    optimized_plan: PlanMetrics

    # Delta (positive = improvement)
    cost_reduction_pct: float        # % reduction in planner cost
    time_reduction_pct: float        # % reduction in execution time
    issues_remaining: list[AntiPattern]  # anti-patterns still present after rewrite

    # LLM metadata
    translation_result: LLMResult    # first LLM call (NL -> SQL)
    optimization_result: LLMResult   # second LLM call (rewrite)
    total_llm_cost_usd: float
    total_llm_latency_ms: float

    # Flags
    improved: bool                   # True if cost went down
    simulate_large: bool


# ── Core function ─────────────────────────────────────────────────────────────

def _extract_metrics(parsed: ParsedPlan) -> PlanMetrics:
    node_types = list(dict.fromkeys(n.node_type for n in parsed.all_nodes))
    return PlanMetrics(
        execution_time_ms=parsed.execution_time_ms,
        planning_time_ms=parsed.planning_time_ms,
        total_cost=parsed.total_cost,
        node_types=node_types,
    )


def _pct_reduction(original: float, optimized: float) -> float:
    """Percentage reduction from original to optimized. Capped at 100%."""
    if original <= 0:
        return 0.0
    reduction = ((original - optimized) / original) * 100
    return round(min(max(reduction, -999.0), 100.0), 2)


def run_optimization_pipeline(
    nl_query: str,
    db_url: str,
    provider: str = "gemini",
    model: Optional[str] = None,
    simulate_large: bool = True,
) -> OptimizationResult:
    """
    Execute the full NL -> SQL -> EXPLAIN -> Detect -> Rewrite -> EXPLAIN pipeline.

    Args:
        nl_query      : Natural language question from the user.
        db_url        : PostgreSQL connection string.
        provider      : LLM provider for both translation and rewrite calls.
        model         : Specific model (uses provider default if None).
        simulate_large: Run EXPLAIN with enable_seqscan=OFF to force index-usage
                        simulation on small datasets.

    Returns:
        OptimizationResult with full before/after comparison data.

    Raises:
        SQLExecutionError  if original or rewritten SQL fails to execute.
        EnvironmentError   if the LLM provider API key is missing.
    """

    # ── Step 1: Schema ────────────────────────────────────────────────────────
    logger.info("Optimization pipeline starting for: %r", nl_query)
    schema = get_schema_info(db_url)

    # ── Step 2: NL -> original SQL ────────────────────────────────────────────
    translation_prompt = build_translation_prompt(schema, nl_query)
    translation_llm = call_llm(
        translation_prompt,
        provider=provider,
        model=model,
        temperature=0.05,
    )
    original_sql = translation_llm.text
    logger.info("Original SQL generated (%d chars)", len(original_sql))

    # ── Step 3: EXPLAIN on original SQL ───────────────────────────────────────
    original_explain = run_explain(original_sql, db_url, simulate_large=simulate_large)
    original_parsed  = parse_explain_output(original_explain)
    original_metrics = _extract_metrics(original_parsed)

    # ── Step 4: Detect anti-patterns ─────────────────────────────────────────
    antipatterns = detect_antipatterns(original_parsed, original_sql)
    logger.info("Detected %d anti-pattern(s)", len(antipatterns))

    # ── Step 5: Build optimization prompt ────────────────────────────────────
    plan_summary_str = summarize_plan(original_parsed)
    ap_descriptions  = [ap.description for ap in antipatterns]

    optimization_prompt = build_optimization_prompt(
        schema=schema,
        original_sql=original_sql,
        antipatterns=ap_descriptions,
        explain_summary=plan_summary_str,
    )

    # ── Step 6: Rewrite SQL ───────────────────────────────────────────────────
    optimization_llm = call_llm(
        optimization_prompt,
        provider=provider,
        model=model,
        temperature=0.20,   # slightly higher for creative restructuring
    )
    optimized_sql = optimization_llm.text
    logger.info("Optimized SQL generated (%d chars)", len(optimized_sql))

    # ── Step 7: EXPLAIN on optimized SQL ─────────────────────────────────────
    optimized_explain = run_explain(optimized_sql, db_url, simulate_large=simulate_large)
    optimized_parsed  = parse_explain_output(optimized_explain)
    optimized_metrics = _extract_metrics(optimized_parsed)

    # ── Step 8: Detect remaining anti-patterns in rewrite ────────────────────
    issues_remaining = detect_antipatterns(optimized_parsed, optimized_sql)

    # ── Step 9: Compute deltas ────────────────────────────────────────────────
    cost_reduction = _pct_reduction(
        original_metrics.total_cost,
        optimized_metrics.total_cost,
    )
    time_reduction = _pct_reduction(
        original_metrics.execution_time_ms,
        optimized_metrics.execution_time_ms,
    )

    total_llm_cost    = translation_llm.cost_usd + optimization_llm.cost_usd
    total_llm_latency = translation_llm.latency_ms + optimization_llm.latency_ms
    improved = optimized_metrics.total_cost < original_metrics.total_cost

    logger.info(
        "Pipeline complete → cost %+.1f%% | time %+.1f%% | improved=%s",
        -cost_reduction, -time_reduction, improved,
    )

    return OptimizationResult(
        nl_query=nl_query,
        original_sql=original_sql,
        original_plan=original_metrics,
        antipatterns=antipatterns,
        optimized_sql=optimized_sql,
        optimized_plan=optimized_metrics,
        cost_reduction_pct=cost_reduction,
        time_reduction_pct=time_reduction,
        issues_remaining=issues_remaining,
        translation_result=translation_llm,
        optimization_result=optimization_llm,
        total_llm_cost_usd=round(total_llm_cost, 8),
        total_llm_latency_ms=round(total_llm_latency, 2),
        improved=improved,
        simulate_large=simulate_large,
    )
