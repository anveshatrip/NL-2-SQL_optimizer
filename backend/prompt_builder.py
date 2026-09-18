
from typing import Dict, Any


def _format_schema_block(schema: Dict[str, Any]) -> str:

    lines = []
    for table, info in schema.items():
        col_str = ", ".join(
            f"{c['name']} ({c['type']})" for c in info["columns"]
        )
        pk_str  = ", ".join(info["primary_key"]) or "(none)"
        idx_str = ", ".join(info["indexes"]) or "(none)"

        lines.append(f"TABLE {table}")
        lines.append(f"  COLUMNS : {col_str}")
        lines.append(f"  PK      : {pk_str}")

        for fk in info["foreign_keys"]:
            fk_cols = ", ".join(fk["columns"])
            lines.append(f"  FK      : {fk_cols} -> {fk['references']}")

        lines.append(f"  INDEXES : {idx_str}")
        lines.append("")  # blank line between tables

    return "\n".join(lines).rstrip()


def build_translation_prompt(schema: Dict[str, Any], nl_query: str) -> str:
    
    schema_block = _format_schema_block(schema)

    prompt = f"""You are an expert PostgreSQL query writer.
Your task is to translate a natural language question into a correct, efficient SQL query.

━━━━━━━━━━━━━━━━━━━━━━ DATABASE SCHEMA ━━━━━━━━━━━━━━━━━━━━━━━━
{schema_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QUESTION: {nl_query}

SQL:"""

    return prompt


def build_optimization_prompt(
    schema: Dict[str, Any],
    original_sql: str,
    antipatterns: list,
    explain_summary: str,
) -> str:
    """
    Builds the prompt sent to Gemini to rewrite a poorly-performing SQL query.
    Used in Phase 2 / 3 (optimization pipeline).
    """
    schema_block = _format_schema_block(schema)
    patterns_str = "\n".join(f"  - {p}" for p in antipatterns) or "  (none detected)"

    prompt = f"""You are a PostgreSQL performance expert.
Rewrite the SQL query below to fix the detected performance anti-patterns.

━━━━━━━━━━━━━━━━━━━━━━ DATABASE SCHEMA ━━━━━━━━━━━━━━━━━━━━━━━━
{schema_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ORIGINAL QUERY:
{original_sql}

EXECUTION PLAN SUMMARY:
{explain_summary}

DETECTED ANTI-PATTERNS:
{patterns_str}


OPTIMIZED SQL:"""

    return prompt
