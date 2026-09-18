import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
    HealthResponse,
    SchemaResponse,
    TranslateRequest,
    TranslateResponse,
    CompareRequest,
    CompareResponse,
    ProviderResult,
)
from schema_introspector import get_schema_info, check_db_connection
from prompt_builder import build_translation_prompt
from llm_client import configure_gemini, call_llm


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("nl2sql")

DB_URL = os.environ.get("DATABASE_URL", "")
APP_VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NL2SQL Optimizer v%s", APP_VERSION)
    if not DB_URL:
        raise EnvironmentError("DATABASE_URL is not set in .env")
    configure_gemini()
    logger.info("Gemini SDK ready")
    yield
    logger.info("Shutting down")

app = FastAPI(
    title="NL2SQL Optimizer",
    description=(
        "Translates natural language to optimized PostgreSQL SQL. "
        "Supports multi-provider comparison: Gemini, OpenAI, Anthropic."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://frontend:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse, tags=["Infra"])
def health_check() -> HealthResponse:
    """Liveness check — returns DB connectivity status."""
    db_ok = check_db_connection(DB_URL)
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
        version=APP_VERSION,
    )


@app.get("/api/schema", response_model=SchemaResponse, tags=["Schema"])
def get_schema() -> SchemaResponse:
    """Reflects the connected PostgreSQL database and returns the full schema."""
    try:
        schema = get_schema_info(DB_URL)
        return SchemaResponse(tables=schema, table_count=len(schema))
    except Exception as exc:
        logger.exception("Schema introspection failed")
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/translate", response_model=TranslateResponse, tags=["Translation"])
def translate(req: TranslateRequest) -> TranslateResponse:
    """
    Translate natural language -> SQL using a single provider.

    Pipeline:
      1. Reflect live schema from PostgreSQL
      2. Build schema-aware prompt
      3. Call chosen LLM provider
      4. Return SQL + token/cost/latency metrics
    """
    logger.info("Translate [%s]: %r", req.provider, req.nl_query)

    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    prompt = build_translation_prompt(schema, req.nl_query)

    try:
        result = call_llm(
            prompt,
            provider=req.provider or "gemini",
            model=req.model,
            temperature=0.05,
        )
    except Exception as exc:
        logger.exception("LLM call failed")
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


@app.post("/api/compare", response_model=CompareResponse, tags=["Comparison"])
def compare(req: CompareRequest) -> CompareResponse:
    """
    Run the same NL query through multiple LLM providers simultaneously
    and return a side-by-side comparison of:
      - Generated SQL
      - Token usage (input + output)
      - Estimated API cost in USD
      - Response latency in ms

    Providers that are not configured (missing API key) are returned
    with an error field instead of crashing the whole request.
    """
    logger.info("Compare across %s: %r", req.providers, req.nl_query)

    try:
        schema = get_schema_info(DB_URL)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB error: {exc}")

    prompt = build_translation_prompt(schema, req.nl_query)

    results: list[ProviderResult] = []
    for provider in (req.providers or ["gemini", "openai", "anthropic"]):
        try:
            r = call_llm(prompt, provider=provider, temperature=0.05)
            results.append(ProviderResult(
                provider=r.provider,
                model=r.model,
                sql=r.text,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                total_tokens=r.input_tokens + r.output_tokens,
                cost_usd=r.cost_usd,
                latency_ms=r.latency_ms,
            ))
        except Exception as exc:
            logger.warning("Provider %s failed: %s", provider, exc)
            results.append(ProviderResult(
                provider=provider,
                model="unavailable",
                sql="",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_usd=0.0,
                latency_ms=0.0,
                error=str(exc),
            ))

    # Identify winners (ignore failed providers)
    successful = [r for r in results if not r.error]
    cheapest = min(successful, key=lambda r: r.cost_usd).provider if successful else None
    fastest  = min(successful, key=lambda r: r.latency_ms).provider if successful else None

    return CompareResponse(
        nl_query=req.nl_query,
        results=results,
        cheapest_provider=cheapest,
        fastest_provider=fastest,
        schema_tables_used=list(schema.keys()),
    )
