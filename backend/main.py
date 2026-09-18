"""
main.py
FastAPI application - NL2SQL Optimizer v0.3.0

Endpoints:
  GET  /health          - Liveness + DB connectivity
  GET  /api/schema      - Full schema introspection
  POST /api/translate   - NL -> SQL (single provider)
  POST /api/analyze     - NL -> SQL -> EXPLAIN -> Anti-patterns (full pipeline)
  POST /api/compare     - NL -> SQL across all providers (cost + latency comparison)
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
    CompareRequest, CompareResponse, ProviderResult,
)
from schema_introspector import get_schema_info, check_db_connection
from prompt_builder import build_translation_prompt
from llm_client import configure_gemini, call_llm
from sql_runner import run_explain, SQLExecutionError
from plan_parser import parse_explain_output, summarize_plan
from antipattern_detector import detect_antipatterns

# ── Bootstrap ─────────────────────────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("nl2sql")

DB_URL = os.environ.get("DATABASE_URL", "")
APP_VERSION = "0.3.0"


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
    description="Schema-aware NL to SQL with multi-provider comparison and query anti-pattern detection.",
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


# ── Routes ────────────────────────────────────────────────────────────────────

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
        nl_query=req.nl_query,
        sql=result.text,
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        schema_tables_used=list(schema.keys()),
    )


@app.post("/api/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
def analyze(req: AnalyzeRequest):
    """
    Full pipeline:
      1. Reflect live schema
      2. Translate NL -> SQL via chosen LLM provider
      3. Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
      4. Parse the execution plan
      5. Detect performance anti-patterns
      6. Return everything in one response
    """
    logger.info("Analyze [%s | simulate=%s]: %r", req.provider, req.simulate_large, req.nl_query)

    # Step 1: Schema
    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    # Step 2: NL -> SQL
    prompt = build_translation_prompt(schema, req.nl_query)
    try:
        llm_result = call_llm(
            prompt,
            provider=req.provider or "gemini",
            model=req.model,
            temperature=0.05,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    sql = llm_result.text
    logger.info("Generated SQL:\n%s", sql)

    # Step 3: EXPLAIN ANALYZE
    try:
        explain_raw = run_explain(sql, DB_URL, simulate_large=req.simulate_large or True)
    except SQLExecutionError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Generated SQL could not be executed: {exc}",
        )

    # Step 4: Parse plan
    parsed = parse_explain_output(explain_raw)

    # Step 5: Detect anti-patterns
    antipatterns = detect_antipatterns(parsed, sql)

    # Step 6: Build response
    node_types = list(dict.fromkeys(n.node_type for n in parsed.all_nodes))

    logger.info(
        "Analysis done → %d anti-patterns, exec=%.2fms, cost=%.2f",
        len(antipatterns), parsed.execution_time_ms, parsed.total_cost,
    )

    return AnalyzeResponse(
        nl_query=req.nl_query,
        sql=sql,
        provider=llm_result.provider,
        model=llm_result.model,
        llm_cost_usd=llm_result.cost_usd,
        llm_latency_ms=llm_result.latency_ms,
        plan=PlanSummary(
            execution_time_ms=parsed.execution_time_ms,
            planning_time_ms=parsed.planning_time_ms,
            total_cost=parsed.total_cost,
            node_types=node_types,
        ),
        antipatterns=[
            AntiPatternInfo(
                pattern_id=ap.pattern_id,
                severity=ap.severity,
                title=ap.title,
                table=ap.table,
                description=ap.description,
                suggestion=ap.suggestion,
            )
            for ap in antipatterns
        ],
        antipattern_count=len(antipatterns),
        has_issues=len(antipatterns) > 0,
        simulate_large=req.simulate_large or True,
    )


@app.post("/api/compare", response_model=CompareResponse, tags=["Comparison"])
def compare(req: CompareRequest):
    """Run the same NL query through multiple providers and compare cost + latency."""
    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    prompt = build_translation_prompt(schema, req.nl_query)
    results = []

    for provider in (req.providers or ["gemini", "openai", "anthropic"]):
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
