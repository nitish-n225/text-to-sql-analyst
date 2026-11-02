"""
Schema Context Builder and Semantic Schema Validator.
Provides:
1. Rich schema context extraction including tables, columns, data types, primary/foreign keys.
2. Low-cardinality categorical enumerations and date ranges to prevent hallucinated values.
3. Explicit multi-table JOIN path instructions.
4. Semantic schema validation to catch hallucinated tables and columns before DB execution.
5. Socratic ambiguity detection for underspecified user queries.
"""

import re
from typing import Dict, Any, List, Optional, Tuple, Set
import sqlglot
from sqlglot import exp
from src.database import DatabaseManager

class SchemaContextBuilder:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._cached_schema: Optional[Dict[str, Any]] = None

    def get_full_schema(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Loads and caches detailed schema with categorical enumerations and date ranges."""
        if self._cached_schema and not force_refresh:
            return self._cached_schema

        summary = self.db_manager.get_schema_summary()
        tables_dict = {tbl["table_name"]: tbl for tbl in summary["tables"]}

        categorical_values: Dict[str, List[str]] = {}
        date_ranges: Dict[str, Dict[str, str]] = {}
        
        conn = self.db_manager.get_readonly_connection()
        try:
            cur = conn.cursor()

            # 1. Check for standard business.db tables if present
            if "customers" in tables_dict:
                try:
                    cur.execute("SELECT DISTINCT loyalty_tier FROM customers WHERE loyalty_tier IS NOT NULL ORDER BY loyalty_tier;")
                    categorical_values["customers.loyalty_tier"] = [r[0] for r in cur.fetchall()]
                    cur.execute("SELECT DISTINCT country FROM customers WHERE country IS NOT NULL ORDER BY country LIMIT 10;")
                    categorical_values["customers.country"] = [r[0] for r in cur.fetchall()]
                except Exception:
                    pass

            if "orders" in tables_dict:
                try:
                    cur.execute("SELECT DISTINCT status FROM orders WHERE status IS NOT NULL ORDER BY status;")
                    categorical_values["orders.status"] = [r[0] for r in cur.fetchall()]
                    cur.execute("SELECT DISTINCT payment_method FROM orders WHERE payment_method IS NOT NULL ORDER BY payment_method;")
                    categorical_values["orders.payment_method"] = [r[0] for r in cur.fetchall()]
                    cur.execute("SELECT MIN(order_date), MAX(order_date) FROM orders;")
                    min_dt, max_dt = cur.fetchone()
                    date_ranges["orders.order_date"] = {"min": str(min_dt), "max": str(max_dt)}
                except Exception:
                    pass

            if "products" in tables_dict:
                try:
                    cur.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category;")
                    categorical_values["products.category"] = [r[0] for r in cur.fetchall()]
                except Exception:
                    pass

            # 2. Dynamic inspection for any uploaded or non-standard tables
            for tbl in summary["tables"]:
                tbl_name = tbl["table_name"]
                for col in tbl["columns"]:
                    col_name = col["name"]
                    col_type = col.get("type", "").upper()
                    full_col_key = f"{tbl_name}.{col_name}"

                    # Detect text categories if not already populated
                    if full_col_key not in categorical_values:
                        if any(t in col_type for t in ["VARCHAR", "TEXT", "CHAR", "STRING"]) and not col_name.lower().endswith("id"):
                            try:
                                cur.execute(f"SELECT DISTINCT [{col_name}] FROM [{tbl_name}] WHERE [{col_name}] IS NOT NULL LIMIT 12;")
                                vals = [str(r[0]) for r in cur.fetchall()]
                                if vals and len(vals) <= 10:
                                    categorical_values[full_col_key] = vals
                            except Exception:
                                pass

                    # Detect date ranges if not already populated
                    if full_col_key not in date_ranges:
                        if any(t in col_type for t in ["DATE", "TIME"]) or "date" in col_name.lower() or "time" in col_name.lower():
                            try:
                                cur.execute(f"SELECT MIN([{col_name}]), MAX([{col_name}]) FROM [{tbl_name}] WHERE [{col_name}] IS NOT NULL;")
                                row = cur.fetchone()
                                if row and row[0] is not None and row[1] is not None:
                                    date_ranges[full_col_key] = {"min": str(row[0]), "max": str(row[1])}
                            except Exception:
                                pass
        finally:
            conn.close()

        # Build relationships and join paths
        is_sample_business_db = {"customers", "orders", "order_items", "products"}.issubset(set(tables_dict.keys()))

        if is_sample_business_db:
            relationships = [
                {
                    "from_table": "orders",
                    "from_column": "customer_id",
                    "to_table": "customers",
                    "to_column": "id",
                    "description": "Each Order is placed by one Customer"
                },
                {
                    "from_table": "order_items",
                    "from_column": "order_id",
                    "to_table": "orders",
                    "to_column": "id",
                    "description": "Each OrderItem belongs to one Order"
                },
                {
                    "from_table": "order_items",
                    "from_column": "product_id",
                    "to_table": "products",
                    "to_column": "id",
                    "description": "Each OrderItem references one Product"
                }
            ]
            join_paths = {
                ("customers", "orders"): "customers c JOIN orders o ON c.id = o.customer_id",
                ("orders", "order_items"): "orders o JOIN order_items oi ON o.id = oi.order_id",
                ("order_items", "products"): "order_items oi JOIN products p ON oi.product_id = p.id",
                ("orders", "products"): "orders o JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id",
                ("customers", "products"): "customers c JOIN orders o ON c.id = o.customer_id JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id"
            }
        else:
            # Dynamically infer foreign key relationships from database schema
            relationships = []
            join_paths = {}
            for tbl in summary["tables"]:
                for fk in tbl.get("foreign_keys", []):
                    ref_tbl = fk.get("referred_table")
                    constrained = fk.get("constrained_columns", [])
                    referred = fk.get("referred_columns", [])
                    if ref_tbl and constrained and referred:
                        c_col = constrained[0]
                        r_col = referred[0]
                        relationships.append({
                            "from_table": tbl["table_name"],
                            "from_column": c_col,
                            "to_table": ref_tbl,
                            "to_column": r_col,
                            "description": f"`{tbl['table_name']}.{c_col}` references `{ref_tbl}.{r_col}`"
                        })
                        join_paths[(tbl["table_name"], ref_tbl)] = f"{tbl['table_name']} JOIN {ref_tbl} ON {tbl['table_name']}.{c_col} = {ref_tbl}.{r_col}"

        self._cached_schema = {
            "tables": tables_dict,
            "categorical_values": categorical_values,
            "date_ranges": date_ranges,
            "relationships": relationships,
            "join_paths": join_paths
        }
        return self._cached_schema

    def build_llm_prompt_context(self, question: Optional[str] = None) -> str:
        """
        Builds a comprehensive, schema-aware system prompt context
        incorporating schema definitions, relationships, join guides, and value dictionaries.
        """
        import os
        schema = self.get_full_schema()
        db_name = os.path.basename(getattr(self.db_manager, "db_path", "database.db"))
        table_count = len(schema["tables"])

        lines = [
            f"### DATABASE SCHEMA (SQLite 3 - {db_name})",
            f"You have access to the following {table_count} relational table(s):",
            ""
        ]

        # Table definitions
        for tbl_name, tbl_info in schema["tables"].items():
            cols = tbl_info["columns"]
            lines.append(f"TABLE `{tbl_name}` (~{tbl_info['row_count']} rows):")
            for c in cols:
                pk_flag = " [PRIMARY KEY]" if c.get("primary_key") else ""
                lines.append(f"  - `{c['name']}` ({c.get('type', 'TEXT')}){pk_flag}")
            lines.append("")

        # Foreign Key Relationships & JOIN Rules
        if schema["relationships"]:
            lines.append("### FOREIGN KEY RELATIONSHIPS & JOIN PATHS:")
            for rel in schema["relationships"]:
                lines.append(f"- `{rel['from_table']}.{rel['from_column']}` -> `{rel['to_table']}.{rel['to_column']}` ({rel['description']})")
            lines.append("")
            if schema["join_paths"]:
                lines.append("Standard Multi-Table JOIN Patterns:")
                for (t1, t2), pattern in schema["join_paths"].items():
                    lines.append(f"- {t1} with {t2}: `FROM {pattern}`")
                lines.append("")
        elif table_count == 1:
            lines.append("### DATASET TYPE: SINGLE-TABLE")
            lines.append("- All analytical queries should target this single table without JOINs.")
            lines.append("")

        # Categorical Values Dictionary
        if schema["categorical_values"]:
            lines.append("### EXACT CATEGORICAL VALUES (Use exact string literals):")
            for k, vals in schema["categorical_values"].items():
                lines.append(f"- `{k}`: {vals}")
            lines.append("")

        if schema["date_ranges"]:
            lines.append("### DATE RANGES:")
            for k, rng in schema["date_ranges"].items():
                lines.append(f"- `{k}` range: {rng['min']} to {rng['max']}")
            lines.append("")

        # SQLite Dialect Best Practices
        lines.append("### SQLITE 3 DIALECT RULES:")
        lines.append("1. Read-Only: Use ONLY `SELECT` or `WITH ... SELECT` queries.")
        lines.append("2. Column quoting: Use brackets `[column]` or standard identifiers.")
        lines.append("3. Aggregations & Rounding: Use `ROUND(SUM(col), 2)` or `ROUND(AVG(col), 2)`.")
        lines.append("4. Grouping & Filtering: Always include non-aggregated selected columns in `GROUP BY`. Use `HAVING` for aggregated filters.")
        lines.append("5. Top-N: Always pair `ORDER BY` with `LIMIT N` when asked for top, highest, or lowest items.")

        return "\n".join(lines)


    def validate_schema_references(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        Validates that all tables and columns referenced in the SQL exist in the actual database schema.
        Prevents hallucinated table names (e.g. 'clients', 'sales', 'items') and column names.
        """
        schema = self.get_full_schema()
        valid_tables: Set[str] = set(schema["tables"].keys())
        
        # Build mapping of table -> column set, plus global columns set
        table_columns: Dict[str, Set[str]] = {}
        all_valid_columns: Set[str] = set()
        for tbl_name, tbl_info in schema["tables"].items():
            cols = {c["name"].lower() for c in tbl_info["columns"]}
            table_columns[tbl_name] = cols
            all_valid_columns.update(cols)

        try:
            parsed = sqlglot.parse_one(sql, read="sqlite")
        except Exception as e:
            return False, f"SQL parsing error during schema validation: {str(e)}"

        # 1. Check all referenced tables
        referenced_tables = [t.name.lower() for t in parsed.find_all(exp.Table) if t.name]
        # Ignore CTE aliases defined in WITH clauses
        with_ctes = set()
        with_expr = parsed.find(exp.With)
        if with_expr:
            for cte in with_expr.expressions:
                if cte.alias:
                    with_ctes.add(cte.alias.lower())

        for tbl in referenced_tables:
            if tbl not in valid_tables and tbl not in with_ctes:
                return False, f"Hallucinated / invalid table '{tbl}'. Valid tables are: {', '.join(sorted(valid_tables))}."

        # 2. Check all referenced columns
        # Check explicit table.column references
        for col in parsed.find_all(exp.Column):
            col_name = col.name.lower() if col.name else ""
            table_qualifier = col.table.lower() if col.table else None

            # Skip asterisk '*'
            if col_name == "*":
                continue

            # If qualified with a real table name
            if table_qualifier and table_qualifier in table_columns:
                if col_name not in table_columns[table_qualifier]:
                    return False, f"Column '{col_name}' does not exist on table '{table_qualifier}'. Valid columns are: {', '.join(sorted(table_columns[table_qualifier]))}."
            # If not qualified, verify it exists somewhere in the database (or is a known column alias/expression)
            elif not table_qualifier and col_name not in all_valid_columns:
                # Check if it was an alias defined in SELECT
                aliases = {s.alias.lower() for s in parsed.find_all(exp.Alias) if s.alias}
                if col_name not in aliases:
                    # Permissive check: column may be a function argument or CTE column
                    # But if clearly absent from entire schema and not an alias, flag it
                    return False, f"Unknown column '{col_name}' referenced in query. Check the schema for correct column names."

        return True, None

    def detect_ambiguity(self, question: str, has_context: bool = False) -> Tuple[bool, Optional[str], List[str]]:
        """
        Identifies whether a natural language question is ambiguous or underspecified,
        providing clarifying questions and options for the user.
        """
        q = question.strip().lower()

        # If this is a conversational follow-up referencing previous turn context
        if has_context and any(w in q for w in ["those", "them", "these", "their", "of which", "instead", "lowest", "top 3", "top 1", "only 3"]):
            return (False, None, [])

        # Check if the query specifies an exact column from the active schema
        schema = self.get_full_schema()
        all_cols = []
        for tbl in schema.get("tables", {}).values():
            all_cols.extend([c["name"].lower() for c in tbl.get("columns", [])])

        column_mentioned = any(c in q or c.replace("_", " ") in q for c in all_cols if len(c) > 2)

        # 1. "Show best" or "what is the best" without defining metric or column
        if re.search(r"\b(best|top|greatest)\b", q) and not column_mentioned and not any(k in q for k in ["spending", "spend", "sales", "revenue", "order", "rating", "rated", "customer", "price", "stock", "margin", "discount", "salary", "amount", "total"]):
            return (
                True,
                "Your request for 'the best' is ambiguous. Which business dimension would you like to evaluate?",
                [
                    "Top products by average customer rating",
                    "Top products by total sales revenue",
                    "Top customers by total spending",
                    "Top categories by product count"
                ]
            )

        # 2. "Show sales" or "recent sales" without metrics or timeframe
        if q in ["sales", "show sales", "revenue", "orders", "show orders"]:
            return (
                True,
                "Would you like to analyze overall order revenue, monthly sales trends, or order status breakdown?",
                [
                    "Total revenue and order count grouped by order status",
                    "Top 5 customers by total spending",
                    "Total sales volume by destination city",
                    "Recent orders with customer names and total amounts"
                ]
            )

        # 3. "Compare tiers" or "which tier" without metric
        if ("loyalty" in q or "tier" in q) and not any(k in q for k in ["count", "number", "spend", "revenue", "order", "average", "distribution"]):
            return (
                True,
                "How would you like to compare customer loyalty tiers?",
                [
                    "Count of customers in each loyalty tier",
                    "Average total spending per customer tier",
                    "Total order volume by customer loyalty tier"
                ]
            )

        return (False, None, [])

