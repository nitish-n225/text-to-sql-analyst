import os
import sqlite3
import time
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

class DatabaseManager:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.active_db = "ecommerce.db"

    def list_databases(self) -> List[Dict[str, Any]]:
        dbs = []
        for f in os.listdir(self.data_dir):
            if f.endswith((".db", ".sqlite", ".sqlite3")):
                full_path = os.path.join(self.data_dir, f)
                stat = os.stat(full_path)
                dbs.append({
                    "filename": f,
                    "name": f.rsplit(".", 1)[0].replace("_", " ").title(),
                    "size_bytes": stat.st_size,
                    "is_active": (f == self.active_db)
                })
        return dbs

    def set_active_db(self, db_name: str) -> bool:
        full_path = os.path.join(self.data_dir, db_name)
        if os.path.exists(full_path):
            self.active_db = db_name
            return True
        return False

    def get_db_path(self, db_name: Optional[str] = None) -> str:
        target = db_name or self.active_db
        return os.path.join(self.data_dir, target)

    def get_connection(self, db_name: Optional[str] = None) -> sqlite3.Connection:
        path = self.get_db_path(db_name)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_schema(self, db_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns full structured schema of the database:
        tables, column details, foreign keys, row counts, and sample records.
        """
        conn = self.get_connection(db_name)
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row["name"] for row in cur.fetchall()]

        schema_info = {
            "database": db_name or self.active_db,
            "tables": []
        }

        for table in tables:
            # Columns
            cur.execute(f"PRAGMA table_info({table});")
            columns_raw = cur.fetchall()
            columns = [{
                "cid": col["cid"],
                "name": col["name"],
                "type": col["type"],
                "notnull": bool(col["notnull"]),
                "pk": bool(col["pk"]),
                "default": col["dflt_value"]
            } for col in columns_raw]

            # Foreign keys
            cur.execute(f"PRAGMA foreign_key_list({table});")
            fks_raw = cur.fetchall()
            fks = [{
                "id": fk["id"],
                "table": fk["table"],
                "from": fk["from"],
                "to": fk["to"]
            } for fk in fks_raw]

            # Row count
            try:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table};")
                row_cnt = cur.fetchone()["cnt"]
            except Exception:
                row_cnt = 0

            # Sample records (top 3)
            try:
                cur.execute(f"SELECT * FROM {table} LIMIT 3;")
                sample_rows = [dict(r) for r in cur.fetchall()]
            except Exception:
                sample_rows = []

            schema_info["tables"].append({
                "table_name": table,
                "row_count": row_cnt,
                "columns": columns,
                "foreign_keys": fks,
                "sample_rows": sample_rows
            })

        conn.close()
        return schema_info

    def get_schema_prompt_string(self, db_name: Optional[str] = None) -> str:
        """
        Formats schema into clear, LLM-friendly DDL and context string.
        """
        schema = self.get_schema(db_name)
        prompt_lines = [f"Database Dialect: SQLite 3", f"Database: {schema['database']}", "Tables and Schema:"]

        for tbl in schema["tables"]:
            col_strs = []
            for col in tbl["columns"]:
                pk_marker = " PRIMARY KEY" if col["pk"] else ""
                col_strs.append(f"  {col['name']} {col['type']}{pk_marker}")
            
            for fk in tbl["foreign_keys"]:
                col_strs.append(f"  FOREIGN KEY ({fk['from']}) REFERENCES {fk['table']}({fk['to']})")

            prompt_lines.append(f"CREATE TABLE {tbl['table_name']} (\n" + ",\n".join(col_strs) + f"\n); -- Contains ~{tbl['row_count']} rows")
            
            if tbl["sample_rows"]:
                sample_cols = [k for k in tbl["sample_rows"][0].keys()]
                sample_str = ", ".join(sample_cols[:6])
                prompt_lines.append(f"-- Example columns in {tbl['table_name']}: {sample_str}")

        return "\n\n".join(prompt_lines)

    def execute_query(self, query: str, db_name: Optional[str] = None, allow_mutation: bool = False) -> Dict[str, Any]:
        """
        Executes a query and returns structured results with execution time and error handling.
        """
        query_stripped = query.strip().rstrip(";")
        clean_upper = query_stripped.upper()

        # Simple safety check in analyst mode
        dangerous_keywords = ["DROP ", "ALTER ", "TRUNCATE ", "DELETE ", "UPDATE ", "INSERT "]
        if not allow_mutation:
            for kw in dangerous_keywords:
                if clean_upper.startswith(kw) or f"; {kw}" in clean_upper:
                    return {
                        "success": False,
                        "error": f"Security Notice: Only read-only queries (SELECT / WITH) are allowed in Analyst Mode. Statement '{kw.strip()}' is blocked.",
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "execution_time_ms": 0.0
                    }

        conn = self.get_connection(db_name)
        cur = conn.cursor()
        start_time = time.time()

        try:
            cur.execute(query_stripped)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            if cur.description:
                columns = [col[0] for col in cur.description]
                rows_raw = cur.fetchall()
                rows = [dict(zip(columns, [r[col] for col in columns])) for r in rows_raw]
                row_count = len(rows)
            else:
                conn.commit()
                columns = ["result"]
                rows = [{"result": f"Affected {cur.rowcount} rows"}]
                row_count = cur.rowcount

            conn.close()
            return {
                "success": True,
                "error": None,
                "columns": columns,
                "rows": rows[:100], # Cap preview to 100 rows for high performance
                "total_rows": row_count,
                "execution_time_ms": elapsed_ms
            }
        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            conn.close()
            return {
                "success": False,
                "error": str(e),
                "columns": [],
                "rows": [],
                "total_rows": 0,
                "execution_time_ms": elapsed_ms
            }

    def explain_query(self, query: str, db_name: Optional[str] = None) -> Dict[str, Any]:
        """Runs EXPLAIN QUERY PLAN on the given SQL statement."""
        explain_sql = f"EXPLAIN QUERY PLAN {query.strip().rstrip(';')}"
        return self.execute_query(explain_sql, db_name=db_name, allow_mutation=False)

    def import_csv(self, file_path: str, table_name: str, db_name: Optional[str] = None) -> Tuple[bool, str]:
        """Imports a CSV file as a new SQLite table."""
        try:
            df = pd.read_csv(file_path)
            conn = self.get_connection(db_name)
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            conn.close()
            return True, f"Successfully imported table '{table_name}' with {len(df)} rows."
        except Exception as e:
            return False, f"CSV import error: {str(e)}"

db_manager = DatabaseManager()
