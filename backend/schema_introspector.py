from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def get_schema_info(db_url: str) -> Dict[str, Any]:
    
    engine = create_engine(db_url)
    inspector = inspect(engine)

    schema: Dict[str, Any] = {}

    for table_name in sorted(inspector.get_table_names()):
        try:
            raw_columns = inspector.get_columns(table_name)
            pk_info     = inspector.get_pk_constraint(table_name)
            fk_list     = inspector.get_foreign_keys(table_name)
            idx_list    = inspector.get_indexes(table_name)

            schema[table_name] = {
                "columns": [
                    {"name": col["name"], "type": str(col["type"])}
                    for col in raw_columns
                ],
                "primary_key": pk_info.get("constrained_columns", []),
                "foreign_keys": [
                    {
                        "columns": fk["constrained_columns"],
                        "references": (
                            f"{fk['referred_table']}"
                            f"({', '.join(fk['referred_columns'])})"
                        ),
                    }
                    for fk in fk_list
                ],
                "indexes": [idx["name"] for idx in idx_list],
            }
        except Exception as exc:
            logger.warning("Could not reflect table %s: %s", table_name, exc)

    engine.dispose()
    return schema


def check_db_connection(db_url: str) -> bool:
    """Lightweight liveness check — returns True if DB is reachable."""
    try:
        engine = create_engine(db_url)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except OperationalError:
        return False
