"""
main.py
FastAPI application - NL2SQL Optimizer v0.4.0

Endpoints:
  GET  /health           - Liveness + DB connectivity
  GET  /api/schema       - Full schema introspection
  POST /api/translate    - NL -> SQL (single provider)
  POST /api/analyze      - NL -> SQL -> EXPLAIN -> Anti-patterns
  POST /api/optimize     - Full pipeline: NL -> SQL -> Detect -> Rewrite -> Before/After diff
  POST /api/compare      - NL -> SQL across all providers (cost + latency comparison)
"""

import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
    HealthResponse, SchemaResponse,
    TranslateRequest, TranslateResponse,
    AnalyzeRequest, AnalyzeResponse, AntiPatternInfo, PlanSummary,
    OptimizeRequest, OptimizeResponse, LLMCallInfo,
    CompareRequest, CompareResponse, ProviderResult,
)
from schema_introspector import get_schema_info, check_db_connection
from prompt_builder import build_translation_prompt
from llm_client import configure_gemini, call_llm
from sql_runner import run_explain, SQLExecutionError
from plan_parser import parse_explain_output
from antipattern_detector import detect_antipatterns
from optimizer import run_optimization_pipeline

# â”€â”€ Bootstrap â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("nl2sql")

DB_URL = os.environ.get("DATABASE_URL", "")
APP_VERSION = "0.4.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NL2SQL Optimizer v%s", APP_VERSION)
    if not DB_URL:
        raise EnvironmentError("DATABASE_URL is not set in .env")
    configure_gemini()
    logger.info("Startup complete")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="NL2SQL Optimizer",
    description=(
        "Schema-aware NL-to-SQL translation with automated query optimization feedback. "
        "Supports Gemini, xAI Grok, and NVIDIA NIM with before/after cost comparison."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# â”€â”€ Helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _ap_to_info(ap) -> AntiPatternInfo:
    return AntiPatternInfo(
        pattern_id=ap.pattern_id,
        severity=ap.severity,
        title=ap.title,
        table=ap.table,
        description=ap.description,
        suggestion=ap.suggestion,
    )


# â”€â”€ Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/health", response_model=HealthResponse, tags=["Infra"])
def health_check():
    db_ok = check_db_connection(DB_URL)
    return HealthResponse(status="ok" if db_ok else "degraded", db_connected=db_ok, version=APP_VERSION)


@app.get("/api/schema", response_model=SchemaResponse, tags=["Schema"])
def get_schema():
    try:
        schema = get_schema_info(DB_URL)
        return SchemaResponse(tables=schema, table_count=len(schema))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/translate", response_model=TranslateResponse, tags=["Translation"])
def translate(req: TranslateRequest):
    """Translate natural language to SQL using a single provider."""
    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    prompt = build_translation_prompt(schema, req.nl_query)

    try:
        result = call_llm(prompt, provider=req.provider or "gemini", model=req.model, temperature=0.05)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    return TranslateResponse(
        nl_query=req.nl_query, sql=result.text,
        provider=result.provider, model=result.model,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        cost_usd=result.cost_usd, latency_ms=result.latency_ms,
        schema_tables_used=list(schema.keys()),
    )


@app.post("/api/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
def analyze(req: AnalyzeRequest):
    """NL -> SQL -> EXPLAIN ANALYZE -> Anti-pattern detection."""
    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    prompt = build_translation_prompt(schema, req.nl_query)
    try:
        llm_result = call_llm(prompt, provider=req.provider or "gemini", model=req.model, temperature=0.05)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    try:
        explain_raw = run_explain(llm_result.text, DB_URL, simulate_large=req.simulate_large or True)
    except SQLExecutionError as exc:
        raise HTTPException(status_code=422, detail=f"SQL execution failed: {exc}")

    parsed      = parse_explain_output(explain_raw)
    antipatterns = detect_antipatterns(parsed, llm_result.text)
    node_types  = list(dict.fromkeys(n.node_type for n in parsed.all_nodes))

    return AnalyzeResponse(
        nl_query=req.nl_query, sql=llm_result.text,
        provider=llm_result.provider, model=llm_result.model,
        llm_cost_usd=llm_result.cost_usd, llm_latency_ms=llm_result.latency_ms,
        plan=PlanSummary(
            execution_time_ms=parsed.execution_time_ms,
            planning_time_ms=parsed.planning_time_ms,
            total_cost=parsed.total_cost,
            node_types=node_types,
        ),
        antipatterns=[_ap_to_info(ap) for ap in antipatterns],
        antipattern_count=len(antipatterns),
        has_issues=len(antipatterns) > 0,
        simulate_large=req.simulate_large or True,
    )


@app.post("/api/optimize", response_model=OptimizeResponse, tags=["Optimization"])
def optimize(req: OptimizeRequest):
    """
    Full optimization pipeline â€” the core research contribution.

    Runs two LLM calls and two EXPLAIN ANALYZE passes to produce a
    measurable before/after cost and execution time comparison.
    """
    logger.info("Optimize [%s | simulate=%s]: %r", req.provider, req.simulate_large, req.nl_query)

    try:
        result = run_optimization_pipeline(
            nl_query=req.nl_query,
            db_url=DB_URL,
            provider=req.provider or "gemini",
            model=req.model,
            simulate_large=req.simulate_large if req.simulate_large is not None else True,
        )
    except SQLExecutionError as exc:
        raise HTTPException(status_code=422, detail=f"SQL execution failed: {exc}")
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Optimization pipeline failed")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    return OptimizeResponse(
        nl_query=result.nl_query,

        # Before
        original_sql=result.original_sql,
        original_plan=PlanSummary(
            execution_time_ms=result.original_plan.execution_time_ms,
            planning_time_ms=result.original_plan.planning_time_ms,
            total_cost=result.original_plan.total_cost,
            node_types=result.original_plan.node_types,
        ),
        antipatterns=[_ap_to_info(ap) for ap in result.antipatterns],
        antipattern_count=len(result.antipatterns),

        # After
        optimized_sql=result.optimized_sql,
        optimized_plan=PlanSummary(
            execution_time_ms=result.optimized_plan.execution_time_ms,
            planning_time_ms=result.optimized_plan.planning_time_ms,
            total_cost=result.optimized_plan.total_cost,
            node_types=result.optimized_plan.node_types,
        ),
        issues_remaining=[_ap_to_info(ap) for ap in result.issues_remaining],
        issues_remaining_count=len(result.issues_remaining),

        # Delta
        cost_reduction_pct=result.cost_reduction_pct,
        time_reduction_pct=result.time_reduction_pct,
        improved=result.improved,

        # LLM metadata
        translation_call=LLMCallInfo(
            provider=result.translation_result.provider,
            model=result.translation_result.model,
            input_tokens=result.translation_result.input_tokens,
            output_tokens=result.translation_result.output_tokens,
            cost_usd=result.translation_result.cost_usd,
            latency_ms=result.translation_result.latency_ms,
        ),
        optimization_call=LLMCallInfo(
            provider=result.optimization_result.provider,
            model=result.optimization_result.model,
            input_tokens=result.optimization_result.input_tokens,
            output_tokens=result.optimization_result.output_tokens,
            cost_usd=result.optimization_result.cost_usd,
            latency_ms=result.optimization_result.latency_ms,
        ),
        total_llm_cost_usd=result.total_llm_cost_usd,
        total_llm_latency_ms=result.total_llm_latency_ms,
        simulate_large=result.simulate_large,
    )


@app.post("/api/compare", response_model=CompareResponse, tags=["Comparison"])
def compare(req: CompareRequest):
    """Run the same NL query through multiple providers, compare cost + latency."""
    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    prompt  = build_translation_prompt(schema, req.nl_query)
    results = []

    for provider in (req.providers or ["gemini", "grok", "nvidia"]):
        try:
            r = call_llm(prompt, provider=provider, temperature=0.05)
            results.append(ProviderResult(
                provider=r.provider, model=r.model, sql=r.text,
                input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                total_tokens=r.input_tokens + r.output_tokens,
                cost_usd=r.cost_usd, latency_ms=r.latency_ms,
            ))
        except Exception as exc:
            logger.warning("Provider %s failed: %s", provider, exc)
            results.append(ProviderResult(
                provider=provider, model="unavailable", sql="",
                input_tokens=0, output_tokens=0, total_tokens=0,
                cost_usd=0.0, latency_ms=0.0, error=str(exc),
            ))

    successful = [r for r in results if not r.error]
    return CompareResponse(
        nl_query=req.nl_query,
        results=results,
        cheapest_provider=min(successful, key=lambda r: r.cost_usd).provider if successful else None,
        fastest_provider=min(successful, key=lambda r: r.latency_ms).provider if successful else None,
        schema_tables_used=list(schema.keys()),
    )
