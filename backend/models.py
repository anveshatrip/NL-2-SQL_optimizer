"""
models.py
Pydantic v2 request/response models for the NL2SQL Optimizer API.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ── Request Models ─────────────────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    nl_query: str = Field(..., min_length=5, examples=["Show all orders from users in India"])
    provider: Optional[str] = Field(default="gemini", description="gemini | openai | anthropic")
    model: Optional[str] = Field(default=None)


class AnalyzeRequest(BaseModel):
    nl_query: str = Field(..., min_length=5, examples=["Show all orders from users in India"])
    provider: Optional[str] = Field(default="gemini")
    model: Optional[str] = Field(default=None)
    simulate_large: Optional[bool] = Field(
        default=True,
        description="Set enable_seqscan=OFF to simulate large-table behaviour on small datasets",
    )


class CompareRequest(BaseModel):
    nl_query: str = Field(..., min_length=5)
    providers: Optional[List[str]] = Field(default=["gemini", "openai", "anthropic"])


# ── Sub-models ────────────────────────────────────────────────────────────────

class ProviderResult(BaseModel):
    provider: str
    model: str
    sql: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    error: Optional[str] = None


class AntiPatternInfo(BaseModel):
    pattern_id: str
    severity: str          # HIGH | MEDIUM | LOW
    title: str
    table: Optional[str]
    description: str
    suggestion: str


class PlanSummary(BaseModel):
    execution_time_ms: float
    planning_time_ms: float
    total_cost: float
    node_types: List[str]  # list of all node types found in the plan tree


# ── Response Models ────────────────────────────────────────────────────────────

class TranslateResponse(BaseModel):
    nl_query: str
    sql: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    schema_tables_used: List[str]


class AnalyzeResponse(BaseModel):
    """Full pipeline response: NL -> SQL -> EXPLAIN -> Anti-patterns."""
    nl_query: str
    sql: str
    provider: str
    model: str
    llm_cost_usd: float
    llm_latency_ms: float
    plan: PlanSummary
    antipatterns: List[AntiPatternInfo]
    antipattern_count: int
    has_issues: bool
    simulate_large: bool


class CompareResponse(BaseModel):
    nl_query: str
    results: List[ProviderResult]
    cheapest_provider: Optional[str]
    fastest_provider: Optional[str]
    schema_tables_used: List[str]


class SchemaResponse(BaseModel):
    tables: Dict[str, Any]
    table_count: int


class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    version: str
