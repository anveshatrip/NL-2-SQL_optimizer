from typing import Dict, Any

def _format_schema_block(schema: Dict[str, Any]) -> str:
    lines = []
    for table, info in schema.items():
        col_str = ", ".join(f"{c['name']} ({c['type']})" for c in info["columns"])
        pk_str  = ", ".join(info["primary_key"]) or "(none)"
        idx_str = ", ".join(info["indexes"]) or "(none)"

        lines.append(f"TABLE {table}")
        lines.append(f"  COLUMNS : {col_str}")
        lines.append(f"  PK      : {pk_str}")
        for fk in info["foreign_keys"]:
            fk_cols = ", ".join(fk["columns"])
            lines.append(f"  FK      : {fk_cols} -> {fk['references']}")
        lines.append(f"  INDEXES : {idx_str}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_translation_prompt(schema: Dict[str, Any], nl_query: str) -> str:
    schema_block = _format_schema_block(schema)
    return f"""You are an expert PostgreSQL query writer.
Translate the following natural language question into a single, valid, complete SQL query.

RULES:
1. Return ONLY the raw SQL query. No explanations, no markdown quotes, no preamble.
2. Use ONLY the tables and columns defined in the schema below.
3. Always use explicit ANSI JOIN syntax (e.g. JOIN ... ON ...), never comma joins.
5. Pay close attention to foreign key and column names in the schema (e.g. use 'user_id', never truncate to 'user' or 'user_').
4. Ensure the query is complete and syntactically valid PostgreSQL.

DATABASE SCHEMA:
{schema_block}

QUESTION: {nl_query}

SQL:"""


def build_optimization_prompt(
    schema: Dict[str, Any],
    original_sql: str,
    antipatterns: list,
    explain_summary: str,
) -> str:
    schema_block = _format_schema_block(schema)
    patterns_str = "\n".join(f"  - {p}" for p in antipatterns) or "  (none detected)"

    return f"""You are a PostgreSQL query optimization expert.
Rewrite the SQL query below to fix the detected performance anti-patterns and reduce execution cost.

RULES:
1. Return ONLY the complete, valid optimized SQL query. No explanation, no markdown backticks.
2. The optimized query MUST return the exact same result set as the original query.
3. Address each detected anti-pattern directly (e.g. use explicit JOINs, replace SELECT * with specific columns, use indexed columns where possible).
4. Do NOT truncate or leave incomplete WHERE clauses. Ensure the statement ends properly with a semicolon.

DATABASE SCHEMA:
{schema_block}

ORIGINAL QUERY:
{original_sql}

EXECUTION PLAN SUMMARY:
{explain_summary}

DETECTED ANTI-PATTERNS:
{patterns_str}

OPTIMIZED SQL:"""
