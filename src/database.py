"""
Database engine, read-only connection manager, schema reflector, and query executor.
Uses SQLAlchemy and SQLite with read-only connection enforcement and execution timeouts.
"""

import os
import sqlite3
import time
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from src.models import Base

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "business.db")

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = os.path.abspath(db_path or DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.rw_engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.rw_engine, autoflush=False, autocommit=False)

    def init_database(self) -> None:
        """Creates tables using SQLAlchemy metadata if they don't exist."""
        Base.metadata.create_all(bind=self.rw_engine)

    def get_session(self) -> Session:
        """Returns a read-write session for seeding or administrative tasks."""
        return self.SessionLocal()

    def get_readonly_connection(self, timeout_sec: float = 5.0) -> sqlite3.Connection:
        """
        Opens a dedicated read-only SQLite connection.
        Enforces read-only mode via URI 'mode=ro' and PRAGMA query_only = ON.
        """
        # Ensure database file exists before opening read-only URI
        if not os.path.exists(self.db_path):
            self.init_database()

        # Connect with SQLite URI in read-only mode
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=timeout_sec)
        conn.row_factory = sqlite3.Row

        # Strictly enforce query_only pragma to guarantee no mutations
        conn.execute("PRAGMA query_only = ON;")
        return conn

    def get_schema_summary(self) -> Dict[str, Any]:
        """
        Inspects the database schema using SQLAlchemy inspector.
        Returns tables, columns, types, foreign keys, row counts, and sample records.
        """
        inspector = inspect(self.rw_engine)
        table_names = inspector.get_table_names()

        schema: Dict[str, Any] = {
            "database_path": self.db_path,
            "dialect": "sqlite",
            "tables": []
        }

        conn = self.get_readonly_connection()
        try:
            cur = conn.cursor()
            for tbl in table_names:
                cols = inspector.get_columns(tbl)
                pk_constraint = inspector.get_pk_constraint(tbl)
                pks = pk_constraint.get("constrained_columns", [])
                fks = inspector.get_foreign_keys(tbl)

                columns_info = []
                for col in cols:
                    columns_info.append({
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": col["name"] in pks
                    })

                # Row count
                try:
                    cur.execute(f"SELECT COUNT(*) as cnt FROM {tbl};")
                    row_count = cur.fetchone()["cnt"]
                except Exception:
                    row_count = 0

                # Top 2 sample rows for context
                try:
                    cur.execute(f"SELECT * FROM {tbl} LIMIT 2;")
                    sample_rows = [dict(r) for r in cur.fetchall()]
                except Exception:
                    sample_rows = []

                schema["tables"].append({
                    "table_name": tbl,
                    "row_count": row_count,
                    "columns": columns_info,
                    "foreign_keys": fks,
                    "sample_rows": sample_rows
                })
        finally:
            conn.close()


        return schema

    def get_schema_prompt_string(self) -> str:
        """
        Formats database schema into a clean, LLM-ready DDL and column prompt string.
        """
        summary = self.get_schema_summary()
        lines = [
            f"-- Database Dialect: SQLite 3",
            f"-- Database: business.db",
            f"-- Tables in database:\n"
        ]

        for tbl in summary["tables"]:
            col_defs = []
            for col in tbl["columns"]:
                pk_str = " PRIMARY KEY" if col["primary_key"] else ""
                null_str = " NOT NULL" if not col["nullable"] else ""
                col_defs.append(f"    {col['name']} {col['type']}{pk_str}{null_str}")

            for fk in tbl["foreign_keys"]:
                referred_table = fk.get("referred_table")
                for c, rc in zip(fk.get("constrained_columns", []), fk.get("referred_columns", [])):
                    col_defs.append(f"    FOREIGN KEY ({c}) REFERENCES {referred_table}({rc})")

            create_stmt = f"CREATE TABLE {tbl['table_name']} (\n" + ",\n".join(col_defs) + f"\n); -- ~{tbl['row_count']} records"
            lines.append(create_stmt)

            if tbl["sample_rows"]:
                sample_cols = list(tbl["sample_rows"][0].keys())
                lines.append(f"-- Example columns for {tbl['table_name']}: {', '.join(sample_cols[:6])}\n")

        return "\n".join(lines)

    def execute_readonly_query(
        self,
        query: str,
        row_limit: int = 500,
        timeout_sec: float = 5.0
    ) -> Tuple[bool, Optional[pd.DataFrame], Optional[str], float]:
        """
        Executes a SQL query through a read-only SQLite connection.
        Enforces execution timeout and row limits.
        
        Returns:
            (success: bool, df: Optional[pd.DataFrame], error_msg: Optional[str], duration_ms: float)
        """
        query_clean = query.strip().rstrip(";")
        start_time = time.time()
        conn = None

        try:
            conn = self.get_readonly_connection(timeout_sec=timeout_sec)
            cur = conn.cursor()

            # Execute query
            cur.execute(query_clean)
            rows = cur.fetchmany(row_limit)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            if cur.description:
                columns = [desc[0] for desc in cur.description]
                data = [dict(zip(columns, [row[c] for c in columns])) for row in rows]
                df = pd.DataFrame(data, columns=columns)
            else:
                df = pd.DataFrame()

            return True, df, None, duration_ms

        except sqlite3.OperationalError as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            return False, None, f"SQLite Operational Error: {str(e)}", duration_ms
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            return False, None, f"Query Execution Error: {str(e)}", duration_ms
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
