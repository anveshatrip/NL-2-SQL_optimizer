"""
models.py
Pydantic v2 request/response models for the NL2SQL Optimizer API.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ── Request Models ─────────────────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    """Payload for NL -> SQL translation (single provider)."""
    nl_query: str = Field(
        ...,
        min_length=5,
        description="Natural language query to translate into SQL",
        examples=["Show me all orders placed by users from India"],
    )
    provider: Optional[str] = Field(
        default="gemini",
        description="LLM provider: 'gemini' | 'openai' | 'anthropic'",
    )
    model: Optional[str] = Field(
        default=None,
        description="Specific model name. If omitted, uses provider default.",
    )


class CompareRequest(BaseModel):
    """Payload for multi-provider comparison run."""
    nl_query: str = Field(
        ...,
        min_length=5,
        description="Natural language query to compare across providers",
    )
    providers: Optional[List[str]] = Field(
        default=["gemini", "openai", "anthropic"],
        description="Which providers to include in the comparison",
    )


# ── Sub-models ────────────────────────────────────────────────────────────────

class ColumnInfo(BaseModel):
    name: str
    type: str


class ForeignKeyInfo(BaseModel):
    columns: List[str]
    references: str


class TableSchema(BaseModel):
    columns: List[ColumnInfo]
    primary_key: List[str]
    foreign_keys: List[ForeignKeyInfo]
    indexes: List[str]


class ProviderResult(BaseModel):
    """Result from a single provider for a comparison run."""
    provider: str
    model: str
    sql: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    error: Optional[str] = None   # set if the provider call failed


# ── Response Models ────────────────────────────────────────────────────────────

class TranslateResponse(BaseModel):
    """Response from NL -> SQL translation (single provider)."""
    nl_query: str
    sql: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    schema_tables_used: List[str]


class CompareResponse(BaseModel):
    """
    Response from a multi-provider comparison.

    The frontend uses this to render the side-by-side comparison table
    with cost and latency bar charts.
    """
    nl_query: str
    results: List[ProviderResult]
    cheapest_provider: Optional[str]
    fastest_provider: Optional[str]
    schema_tables_used: List[str]


class SchemaResponse(BaseModel):
    """Full schema introspection result."""
    tables: Dict[str, Any]
    table_count: int


class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    version: str
