"""
plan_parser.py
Parses the JSON output of PostgreSQL EXPLAIN (ANALYZE, FORMAT JSON) into
structured Python objects that the anti-pattern detector can reason over.

PostgreSQL EXPLAIN JSON has a recursive "Plans" array — this module
flattens the entire tree into a list of PlanNode objects while preserving
parent-child relationships for context.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PlanNode:
    """One node in the PostgreSQL query execution plan tree."""
    node_type: str                        # e.g. "Seq Scan", "Hash Join", "Index Scan"
    relation_name: Optional[str]          # table name (only on scan nodes)
    alias: Optional[str]                  # table alias used in query
    startup_cost: float                   # planner estimated startup cost
    total_cost: float                     # planner estimated total cost
    plan_rows: int                        # planner estimated rows
    actual_rows: int                      # rows actually returned at runtime
    actual_time_ms: float                 # actual total time in ms
    rows_removed_by_filter: int           # rows scanned but thrown away
    filter_expr: Optional[str]            # WHERE filter applied at this node
    index_name: Optional[str]             # index used (Index Scan nodes only)
    join_filter: Optional[str]            # join condition (join nodes only)
    children: list[PlanNode] = field(default_factory=list)


@dataclass
class ParsedPlan:
    """Fully parsed EXPLAIN output with a flat node list for easy analysis."""
    root: PlanNode
    planning_time_ms: float
    execution_time_ms: float
    total_cost: float
    all_nodes: list[PlanNode]             # every node flattened (DFS order)


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_node(raw: dict[str, Any]) -> PlanNode:
    """Recursively parse one plan node and all its children."""
    actual_loops = max(raw.get("Actual Loops", 1), 1)

    node = PlanNode(
        node_type=raw.get("Node Type", "Unknown"),
        relation_name=raw.get("Relation Name"),
        alias=raw.get("Alias"),
        startup_cost=raw.get("Startup Cost", 0.0),
        total_cost=raw.get("Total Cost", 0.0),
        plan_rows=raw.get("Plan Rows", 0),
        actual_rows=int(raw.get("Actual Rows", 0) * actual_loops),
        actual_time_ms=round(raw.get("Actual Total Time", 0.0), 3),
        rows_removed_by_filter=int(
            raw.get("Rows Removed by Filter", 0) * actual_loops
        ),
        filter_expr=raw.get("Filter"),
        index_name=raw.get("Index Name"),
        join_filter=raw.get("Join Filter"),
    )

    for child_raw in raw.get("Plans", []):
        node.children.append(_parse_node(child_raw))

    return node


def _flatten(node: PlanNode, out: list[PlanNode]) -> None:
    """DFS traversal to collect all nodes into a flat list."""
    out.append(node)
    for child in node.children:
        _flatten(child, out)


def parse_explain_output(explain_result: dict[str, Any]) -> ParsedPlan:
    """
    Parse the dict returned by sql_runner.run_explain() into a ParsedPlan.

    Args:
        explain_result: Output of run_explain() — contains 'plan', timing, cost.

    Returns:
        ParsedPlan with root node, flat node list, and timing info.
    """
    raw_plan = explain_result["plan"]

    # PostgreSQL wraps the plan in a list with one element
    plan_wrapper = raw_plan[0] if isinstance(raw_plan, list) else raw_plan
    root_raw = plan_wrapper.get("Plan", plan_wrapper)

    root = _parse_node(root_raw)

    all_nodes: list[PlanNode] = []
    _flatten(root, all_nodes)

    return ParsedPlan(
        root=root,
        planning_time_ms=explain_result.get("planning_time", 0.0),
        execution_time_ms=explain_result.get("execution_time", 0.0),
        total_cost=explain_result.get("total_cost", 0.0),
        all_nodes=all_nodes,
    )


# ── Summary helper (for LLM optimization prompt) ──────────────────────────────

def summarize_plan(parsed: ParsedPlan) -> str:
    """
    Produce a short human-readable summary of the plan for injection
    into the LLM optimization prompt.
    """
    lines = [
        f"Execution Time  : {parsed.execution_time_ms:.2f} ms",
        f"Planning Time   : {parsed.planning_time_ms:.2f} ms",
        f"Total Cost      : {parsed.total_cost:.2f} (planner units)",
        "",
        "Node breakdown:",
    ]
    for node in parsed.all_nodes:
        table = f" on {node.relation_name}" if node.relation_name else ""
        removed = (
            f" | {node.rows_removed_by_filter} rows removed by filter"
            if node.rows_removed_by_filter > 0
            else ""
        )
        lines.append(
            f"  [{node.node_type}{table}] "
            f"actual={node.actual_rows} rows, "
            f"time={node.actual_time_ms:.2f}ms"
            f"{removed}"
        )
    return "\n".join(lines)
