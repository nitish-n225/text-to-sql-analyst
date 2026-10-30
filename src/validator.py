"""
Robust SQL Query Validator using sqlglot AST parsing.
Enforces:
1. Exactly one single statement.
2. Read-only SELECT or safe read-only WITH CTE queries only.
3. Strict blocking of write operations, DDL, DML, multiple statements, and unsafe constructs.
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Set
import sqlglot
from sqlglot import exp

@dataclass
class ValidationResult:
    is_valid: bool
    error_message: Optional[str] = None
    sanitized_sql: Optional[str] = None

# Blocked AST Node types that represent modifications, administrative, or destructive actions
FORBIDDEN_EXPRESSION_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Pragma,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Set,
)

# Unsafe SQLite functions / procedures
DANGEROUS_FUNCTIONS: Set[str] = {
    "load_extension",
    "writefile",
    "readfile",
    "edit",
    "fts3_tokenizer",
    "schema",
    "eval"
}

def clean_sql_text(raw_sql: str) -> str:
    """Strips markdown code blocks, backticks, and trailing whitespace/semicolons."""
    text = raw_sql.strip()
    # Remove markdown code block if present
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    return text

def validate_sql(raw_sql: str) -> ValidationResult:
    """
    Parses and verifies that the provided query is safe, strictly read-only,
    contains exactly one statement, and performs no destructive operations.
    """
    if not raw_sql or not raw_sql.strip():
        return ValidationResult(is_valid=False, error_message="Empty query provided.")

    cleaned = clean_sql_text(raw_sql)

    # 1. Reject multiple statements separated by semicolons
    # A single trailing semicolon is allowed, but not multiple statements
    trailing_removed = cleaned.rstrip(";").strip()
    if ";" in trailing_removed:
        # Check if the semicolon is part of multiple queries
        # (e.g. "SELECT 1; DROP TABLE users")
        return ValidationResult(
            is_valid=False,
            error_message="Multiple statements detected. Only a single query is permitted."
        )

    # 2. Parse using sqlglot
    try:
        parsed_statements: List[Optional[exp.Expression]] = sqlglot.parse(cleaned, read="sqlite")
    except Exception as parse_err:
        return ValidationResult(
            is_valid=False,
            error_message=f"SQL Syntax / Parsing Error: {str(parse_err)}"
        )

    # Filter out empty statements
    statements = [s for s in parsed_statements if s is not None]

    if not statements:
        return ValidationResult(is_valid=False, error_message="No valid SQL statement found.")

    if len(statements) > 1:
        return ValidationResult(
            is_valid=False,
            error_message="Multiple statements detected. Only a single query is permitted."
        )

    root = statements[0]

    # 3. Check Root Statement Type
    # Must be Select, or an expression where this is a Select (e.g. WITH cte AS (...) SELECT ...)
    is_select = isinstance(root, exp.Select)
    is_with_select = isinstance(root, exp.Expression) and root.find(exp.Select) is not None and not isinstance(root, FORBIDDEN_EXPRESSION_TYPES)

    if not (is_select or is_with_select):
        type_name = root.__class__.__name__
        return ValidationResult(
            is_valid=False,
            error_message=f"Forbidden operation '{type_name}'. Only read-only SELECT or WITH queries are permitted."
        )

    # 4. AST Recursive Walk - Inspect ALL nodes in the tree
    for node in root.walk():
        # Check for forbidden mutation expressions
        if isinstance(node, FORBIDDEN_EXPRESSION_TYPES):
            node_type = node.__class__.__name__
            return ValidationResult(
                is_valid=False,
                error_message=f"Destructive or mutating operation '{node_type}' is strictly blocked."
            )

        # Check for PRAGMA, ATTACH, DETACH
        if isinstance(node, exp.Command):
            return ValidationResult(
                is_valid=False,
                error_message="Administrative / Command operations are strictly blocked."
            )

        # Check for dangerous function calls
        if isinstance(node, exp.Anonymous):
            func_name = node.this.lower() if isinstance(node.this, str) else ""
            if func_name in DANGEROUS_FUNCTIONS:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Security alert: Function '{func_name}' is blocked."
                )

    # 5. Additional keyword safety scan for unparsed SQLite special commands
    raw_upper = cleaned.upper()
    unparsed_forbidden = [
        "PRAGMA ", "ATTACH ", "DETACH ", "VACUUM", "REINDEX",
        "ALTER ", "DROP ", "TRUNCATE ", "INSERT ", "UPDATE ", "DELETE "
    ]
    # Check if keyword is used as a statement starter or outside string literals
    for kw in unparsed_forbidden:
        if raw_upper.startswith(kw) or f"; {kw}" in raw_upper:
            return ValidationResult(
                is_valid=False,
                error_message=f"Security alert: Statement '{kw.strip()}' is blocked."
            )

    # Return valid normalized query
    return ValidationResult(
        is_valid=True,
        error_message=None,
        sanitized_sql=trailing_removed
    )
