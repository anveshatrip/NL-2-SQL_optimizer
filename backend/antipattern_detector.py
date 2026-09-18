"""
antipattern_detector.py
Rule-based engine that inspects a ParsedPlan + the original SQL string
and flags performance anti-patterns.

Each rule is a standalone function returning a list of AntiPattern objects
(empty list = no issue found). The main entry point detect_antipatterns()
runs all rules and merges the results.

Severity levels:
  HIGH   - will almost certainly cause severe slowdown at scale
  MEDIUM - likely to cause slowdown, investigate
  LOW    - minor inefficiency or style issue
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from plan_parser import ParsedPlan, PlanNode


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class AntiPattern:
    pattern_id: str              # machine-readable code, e.g. "SEQ_SCAN"
    severity: str                # "HIGH" | "MEDIUM" | "LOW"
    title: str                   # short display label
    table: Optional[str]         # which table is affected (if applicable)
    description: str             # what the problem is
    suggestion: str              # how to fix it


# ── Individual rules ──────────────────────────────────────────────────────────

def _rule_seq_scan(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Detect Sequential (Full) Table Scans.
    A Seq Scan reads every row in a table — at scale this is catastrophic.
    On our small dataset we still flag it to educate and because adding an
    index is always the right call on a join/filter column.
    """
    found = []
    for node in parsed.all_nodes:
        if node.node_type == "Seq Scan" and node.relation_name:
            found.append(AntiPattern(
                pattern_id="SEQ_SCAN",
                severity="HIGH",
                title="Full Table Scan",
                table=node.relation_name,
                description=(
                    f"A Sequential Scan is being performed on table "
                    f"'{node.relation_name}'. Every row is read from disk "
                    f"({node.actual_rows} rows scanned). At scale this "
                    f"grows linearly with table size."
                ),
                suggestion=(
                    f"Add an index on the column(s) used in the WHERE or JOIN "
                    f"condition on '{node.relation_name}'. "
                    f"Example: CREATE INDEX ON {node.relation_name}(<join_or_filter_column>);"
                ),
            ))
    return found


def _rule_rows_removed(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Detect nodes where far more rows are scanned than returned (low selectivity).
    A ratio > 10:1 (removed:returned) suggests a missing or unused index.
    """
    found = []
    for node in parsed.all_nodes:
        removed = node.rows_removed_by_filter
        returned = max(node.actual_rows, 1)
        if removed > 0 and (removed / returned) > 10:
            found.append(AntiPattern(
                pattern_id="HIGH_FILTER_COST",
                severity="MEDIUM",
                title="High Row Filter Waste",
                table=node.relation_name,
                description=(
                    f"Node '{node.node_type}'"
                    + (f" on '{node.relation_name}'" if node.relation_name else "")
                    + f" removed {removed} rows but only returned {node.actual_rows}. "
                    f"The filter '{node.filter_expr}' is scanning far more data than needed."
                ),
                suggestion=(
                    "Consider adding an index on the filtered column, or rewriting "
                    "the WHERE clause to be more selective earlier in the query."
                ),
            ))
    return found


def _rule_select_star(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """Detect SELECT * usage — fetches unnecessary columns and blocks index-only scans."""
    if re.search(r"SELECT\s+\*", sql, re.IGNORECASE):
        return [AntiPattern(
            pattern_id="SELECT_STAR",
            severity="MEDIUM",
            title="SELECT * Used",
            table=None,
            description=(
                "The query uses SELECT *, which fetches every column from every "
                "joined table. This prevents index-only scans, increases memory "
                "usage, and transfers unnecessary data over the network."
            ),
            suggestion=(
                "Replace SELECT * with only the columns your application needs. "
                "Example: SELECT u.name, o.total, o.created_at ..."
            ),
        )]
    return []


def _rule_leading_wildcard(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Detect non-SARGable LIKE patterns with a leading wildcard.
    LIKE '%value' cannot use a B-tree index — forces full scan.
    """
    if re.search(r"LIKE\s+['\"]%[^%]", sql, re.IGNORECASE):
        return [AntiPattern(
            pattern_id="LIKE_LEADING_WILDCARD",
            severity="HIGH",
            title="Leading Wildcard in LIKE",
            table=None,
            description=(
                "A LIKE pattern starting with '%' (e.g. LIKE '%smith') is "
                "non-SARGable — PostgreSQL cannot use a B-tree index to evaluate "
                "it and must perform a full table scan."
            ),
            suggestion=(
                "If suffix search is required, use a pg_trgm GIN index: "
                "CREATE INDEX ON table USING gin(column gin_trgm_ops). "
                "Otherwise, rewrite as LIKE 'value%' if a prefix match suffices."
            ),
        )]
    return []


def _rule_implicit_cross_join(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Detect implicit Cartesian products from comma-separated tables
    without a proper WHERE join condition.
    Pattern: FROM a, b with no ON or WHERE linking them.
    """
    # Look for comma-joined tables in FROM clause without explicit JOIN
    from_match = re.search(
        r"FROM\s+\w+\s*,\s*\w+",
        sql,
        re.IGNORECASE,
    )
    if from_match and "JOIN" not in sql.upper():
        return [AntiPattern(
            pattern_id="CARTESIAN_PRODUCT",
            severity="HIGH",
            title="Implicit Cartesian Product",
            table=None,
            description=(
                "The query uses comma-separated tables in the FROM clause "
                "(e.g. FROM users, orders) without an explicit JOIN condition. "
                "This produces a Cartesian product — every row from table A "
                "is paired with every row from table B, multiplying row counts."
            ),
            suggestion=(
                "Replace comma joins with explicit JOIN ... ON syntax: "
                "FROM users u JOIN orders o ON u.id = o.user_id"
            ),
        )]
    return []


def _rule_nested_loop_large(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Detect Nested Loop joins with a large number of actual rows.
    Nested Loops are O(n*m) — fine for small tables, catastrophic for large ones.
    """
    found = []
    for node in parsed.all_nodes:
        if node.node_type == "Nested Loop" and node.actual_rows > 500:
            found.append(AntiPattern(
                pattern_id="NESTED_LOOP_LARGE",
                severity="MEDIUM",
                title="Nested Loop on Large Row Set",
                table=None,
                description=(
                    f"A Nested Loop join produced {node.actual_rows} rows. "
                    f"Nested Loops are O(n×m) — this will degrade severely "
                    f"as data grows. PostgreSQL may have chosen this because "
                    f"statistics are stale or an index is missing."
                ),
                suggestion=(
                    "Ensure join columns are indexed on both sides. Run "
                    "ANALYZE on the involved tables to refresh planner statistics. "
                    "Consider a Hash Join by ensuring both tables are large enough "
                    "for the planner to prefer it."
                ),
            ))
    return found


def _rule_missing_join_index(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Detect Seq Scans that occur specifically inside a join context —
    a strong signal of a missing index on a foreign key column.
    """
    found = []
    join_node_types = {"Hash Join", "Nested Loop", "Merge Join"}
    has_join = any(n.node_type in join_node_types for n in parsed.all_nodes)

    if has_join:
        for node in parsed.all_nodes:
            if node.node_type == "Seq Scan" and node.relation_name:
                found.append(AntiPattern(
                    pattern_id="MISSING_FK_INDEX",
                    severity="HIGH",
                    title="Missing Index on Join Column",
                    table=node.relation_name,
                    description=(
                        f"Table '{node.relation_name}' is being fully scanned "
                        f"as part of a JOIN. This typically means the join column "
                        f"(usually a foreign key) has no index, forcing a sequential "
                        f"scan on every join iteration."
                    ),
                    suggestion=(
                        f"Add an index on the foreign key column used to join "
                        f"'{node.relation_name}'. "
                        f"Example: CREATE INDEX ON {node.relation_name}(user_id); "
                        f"or whatever FK column is in the ON clause."
                    ),
                ))
    return found


# ── Main entry point ──────────────────────────────────────────────────────────

_RULES = [
    _rule_seq_scan,
    _rule_rows_removed,
    _rule_select_star,
    _rule_leading_wildcard,
    _rule_implicit_cross_join,
    _rule_nested_loop_large,
    _rule_missing_join_index,
]


def detect_antipatterns(parsed: ParsedPlan, sql: str) -> list[AntiPattern]:
    """
    Run all detection rules against a parsed EXPLAIN plan + original SQL.

    Returns a deduplicated list of AntiPattern objects ordered by severity
    (HIGH first, then MEDIUM, then LOW).
    """
    all_found: list[AntiPattern] = []
    seen_ids: set[str] = set()

    for rule in _RULES:
        for ap in rule(parsed, sql):
            # Deduplicate by (pattern_id, table) pair
            key = f"{ap.pattern_id}:{ap.table}"
            if key not in seen_ids:
                all_found.append(ap)
                seen_ids.add(key)

    # Sort: HIGH → MEDIUM → LOW
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_found.sort(key=lambda x: severity_order.get(x.severity, 3))

    return all_found
