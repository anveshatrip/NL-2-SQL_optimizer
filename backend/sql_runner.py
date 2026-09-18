"""
sql_runner.py
Executes SQL queries against PostgreSQL and retrieves EXPLAIN ANALYZE output.

Two modes:
  normal   : EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) - uses real planner decisions
  simulate : Same but with enable_seqscan=OFF, forcing the planner to use indexes
             even on small tables. Used to demonstrate what performance would look
             like at scale (documented as "scale-simulated evaluation").
"""

import logging
from typing import Any
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class SQLExecutionError(Exception):
    """Raised when a query fails to execute (syntax error, bad table, etc.)."""
    pass


def _is_select(sql: str) -> bool:
    """Guard: only allow SELECT queries through EXPLAIN ANALYZE."""
    cleaned = sql.strip().lstrip("(").upper()
    return cleaned.startswith("SELECT") or cleaned.startswith("WITH")


def run_explain(
    sql: str,
    db_url: str,
    simulate_large: bool = False,
) -> dict[str, Any]:
    """
    Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) on a SQL query.

    Args:
        sql           : The SELECT query to analyze.
        db_url        : PostgreSQL connection string.
        simulate_large: If True, sets enable_seqscan=OFF before running,
                        which forces index usage and simulates large-table behaviour.

    Returns:
        {
          "plan"          : <full EXPLAIN JSON list>,
          "execution_time": <float ms>,
          "planning_time" : <float ms>,
          "total_cost"    : <float, planner estimated cost units>,
        }

    Raises:
        SQLExecutionError if the query fails.
    """
    if not _is_select(sql):
        raise SQLExecutionError(
            "Only SELECT queries are allowed through EXPLAIN ANALYZE. "
            "Received a non-SELECT statement."
        )

    engine = create_engine(db_url)
    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"

    try:
        with engine.connect() as conn:
            if simulate_large:
                conn.execute(text("SET enable_seqscan = OFF"))
                logger.info("Simulation mode: enable_seqscan=OFF")

            result = conn.execute(text(explain_sql))
            rows = result.fetchall()

            # PostgreSQL returns the JSON plan as a single column, single row
            plan = rows[0][0]  # This is already a Python list/dict from psycopg2

            # Extract top-level timing from the plan wrapper
            execution_time = plan[0].get("Execution Time", 0.0)
            planning_time  = plan[0].get("Planning Time", 0.0)
            total_cost     = plan[0]["Plan"].get("Total Cost", 0.0)

            logger.info(
                "EXPLAIN done → exec=%.2fms plan=%.2fms cost=%.2f",
                execution_time, planning_time, total_cost,
            )

            return {
                "plan":           plan,
                "execution_time": round(execution_time, 3),
                "planning_time":  round(planning_time, 3),
                "total_cost":     round(total_cost, 4),
            }

    except Exception as exc:
        error_msg = str(exc)
        logger.warning("EXPLAIN failed: %s", error_msg)
        raise SQLExecutionError(f"Query execution failed: {error_msg}") from exc
    finally:
        engine.dispose()
