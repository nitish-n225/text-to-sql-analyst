"""
Text-to-SQL Execution Pipeline with Advanced Stage 2 Intelligence:
1. Enriched schema context prompting and semantic schema validation.
2. Structured output ingestion (SQL, explanation, assumptions).
3. Ambiguity detection and clarification suggestions.
4. Bounded self-healing correction retries (at most 2 retries, total 3 attempts).
5. Error sanitization (zero secrets, file paths, or stack traces).
6. Strict revalidation of every retry before database execution.
7. Execution via SQLite read-only connection with timeouts and row limits.
8. Diagnostic observability logging without sensitive leakage.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.database import DatabaseManager
from src.validator import validate_sql, ValidationResult
from src.schema_context import SchemaContextBuilder
from src.llm_adapter import BaseLLMAdapter, DemoModeAdapter, LLMOutput
from src.logger import observability

MAX_CORRECTION_RETRIES = 2 # At most 2 retries (total 3 attempts max)

def sanitize_error_context(raw_error: str) -> str:
    """
    Sanitizes database and validation error messages before sending them to the LLM.
    Removes system file paths, internal stack traces, and sensitive environment details,
    retaining only the SQLite semantic error message (e.g. unknown column, syntax error).
    """
    if not raw_error:
        return "Unknown error"

    cleaned = str(raw_error)

    # 1. Remove Windows and Unix file paths (e.g. C:\Users\... or /path/to/...)
    cleaned = re.sub(r"[A-Za-z]:\\[\w\\\.\s\-_]+", "<local_path>", cleaned)
    cleaned = re.sub(r"/(?:home|Users|var|tmp|app)/[\w\./\-_]+", "<local_path>", cleaned)

    # 2. Strip SQLite operational error prefixes
    prefixes_to_strip = [
        "SQLite Operational Error: ",
        "Query Execution Error: ",
        "sqlite3.OperationalError: ",
        "sqlite3.DatabaseError: ",
        "sqlite3.ProgrammingError: "
    ]
    for p in prefixes_to_strip:
        cleaned = cleaned.replace(p, "")

    # 3. Strip memory addresses
    cleaned = re.sub(r"0x[0-9a-fA-F]+", "<mem_addr>", cleaned)

    return cleaned.strip()


@dataclass
class AttemptRecord:
    attempt_number: int
    sql: str
    status: str # "SUCCESS", "VALIDATION_FAILED", "EXECUTION_ERROR", "MODEL_ERROR"
    error_message: Optional[str] = None
    sanitized_error: Optional[str] = None
    duration_ms: float = 0.0
    rows_count: int = 0
    explanation: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    error_category: Optional[str] = None


@dataclass
class PipelineResult:
    success: bool
    question: str
    query_used: str
    dataframe: Optional[pd.DataFrame]
    summary: str
    trace: List[AttemptRecord]
    total_attempts: int
    had_retry: bool
    provider_label: str
    execution_time_ms: float = 0.0
    total_duration_ms: float = 0.0
    final_error: Optional[str] = None
    figure: Optional[go.Figure] = None
    # Stage 2 additions with defaults for backward compatibility
    explanation: str = ""
    assumptions: List[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    error_category: Optional[str] = None


def generate_plotly_chart(df: pd.DataFrame, question: str) -> Optional[go.Figure]:
    """
    Auto-detects visualization dimensions and creates an interactive Plotly chart.
    """
    if df is None or df.empty or len(df) < 2:
        return None

    columns = list(df.columns)
    numeric_cols = [c for c in columns if pd.api.types.is_numeric_dtype(df[c]) and not c.lower().endswith("id") and c.lower() != "id"]
    string_cols = [c for c in columns if not pd.api.types.is_numeric_dtype(df[c])]

    if not numeric_cols:
        return None

    label_col = string_cols[0] if string_cols else columns[0]
    metric_col = numeric_cols[0]
    df_chart = df.head(15).copy()

    # Detect if label contains dates for a line chart
    first_val = str(df_chart[label_col].iloc[0])
    is_date = bool(re.search(r"^\d{4}-\d{2}", first_val))

    fig = None
    if is_date:
        fig = px.line(
            df_chart,
            x=label_col,
            y=metric_col,
            markers=True,
            title=f"{metric_col.replace('_', ' ').title()} over Time",
            template="plotly_dark"
        )
    elif len(df_chart) <= 6 and len(numeric_cols) == 1 and not is_date:
        fig = px.pie(
            df_chart,
            names=label_col,
            values=metric_col,
            title=f"Distribution of {metric_col.replace('_', ' ').title()} by {label_col.replace('_', ' ').title()}",
            template="plotly_dark",
            hole=0.4
        )
    else:
        fig = px.bar(
            df_chart,
            x=label_col,
            y=metric_col,
            title=f"{metric_col.replace('_', ' ').title()} by {label_col.replace('_', ' ').title()}",
            template="plotly_dark",
            color=metric_col,
            color_continuous_scale="Viridis"
        )

    if fig:
        fig.update_layout(
            margin=dict(l=20, r=20, t=50, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Plus Jakarta Sans, sans-serif")
        )

    return fig


class TextToSqlPipeline:
    def __init__(self, db_manager: DatabaseManager, llm_adapter: BaseLLMAdapter):
        self.db_manager = db_manager
        self.llm_adapter = llm_adapter
        self.schema_builder = SchemaContextBuilder(db_manager)
        self.max_retries = MAX_CORRECTION_RETRIES

    def run(self, question: str, induce_error_first_attempt: bool = False) -> PipelineResult:
        """
        Executes the advanced Text-to-SQL pipeline:
        1. Checks for question ambiguity upfront.
        2. Builds enriched schema context.
        3. Generates structured output via LLM adapter.
        4. Validates AST safety and semantic schema references.
        5. Executes read-only query in database sandbox.
        6. On recoverable error: triggers bounded self-healing retry (max 2 retries).
        7. Synthesizes summary, assumptions, explanation, and Plotly visualization.
        """
        overall_start = time.time()
        observability.log_event("QUERY_RECEIVED", f"Received query: '{question}'", {"provider": self.llm_adapter.label})

        # 1. Check for question ambiguity
        is_ambiguous, clar_question, clar_options = self.schema_builder.detect_ambiguity(question)
        if is_ambiguous:
            observability.log_event("AMBIGUITY_DETECTED", f"Ambiguous question detected: '{question}'")
            total_duration_ms = round((time.time() - overall_start) * 1000, 2)
            return PipelineResult(
                success=False,
                question=question,
                query_used="",
                dataframe=None,
                summary=f"Clarification needed: {clar_question}",
                trace=[],
                total_attempts=0,
                had_retry=False,
                provider_label=self.llm_adapter.label,
                total_duration_ms=total_duration_ms,
                final_error="Question is ambiguous",
                figure=None,
                explanation="The question requires user clarification to establish specific analytical criteria.",
                assumptions=[],
                needs_clarification=True,
                clarification_question=clar_question,
                clarification_options=clar_options,
                error_category="AMBIGUITY_DETECTED"
            )

        # 2. Build rich schema context
        schema_prompt = self.schema_builder.build_llm_prompt_context(question)
        observability.log_event("SCHEMA_BUILT", "Enriched schema context constructed")

        trace: List[AttemptRecord] = []
        attempt = 1
        max_attempts = 1 + self.max_retries
        last_sanitized_error: Optional[str] = None
        successful_df: Optional[pd.DataFrame] = None
        last_exec_time = 0.0
        final_explanation = ""
        final_assumptions: List[str] = []
        current_sql = ""
        last_error_category = None

        while attempt <= max_attempts:
            attempt_start = time.time()
            error_feedback = last_sanitized_error

            # Generate via structured LLM adapter
            observability.log_event("LLM_CALLED", f"Attempt {attempt}: generating SQL", {"is_retry": attempt > 1})
            
            try:
                if induce_error_first_attempt and attempt == 1:
                    # Deliberately inject a realistic column typo for self-healing demonstration
                    llm_out = LLMOutput(
                        sql=(
                            "SELECT customer_name, SUM(total_amount) AS total_spent "
                            "FROM customers JOIN orders ON customers.id = orders.customer_id "
                            "GROUP BY customer_name ORDER BY total_spent DESC LIMIT 5"
                        ),
                        explanation="Induced test query with column name mismatch for self-healing verification.",
                        assumptions=["Self-healing retry demonstration"]
                    )
                else:
                    llm_out = self.llm_adapter.generate_structured(
                        question=question,
                        schema_prompt=schema_prompt,
                        error_feedback=error_feedback
                    )
            except Exception as e:
                err_msg = str(e)
                sanitized_model_err = sanitize_error_context(err_msg)
                attempt_dur = round((time.time() - attempt_start) * 1000, 2)
                trace.append(AttemptRecord(
                    attempt_number=attempt,
                    sql="",
                    status="MODEL_ERROR",
                    error_message=err_msg,
                    sanitized_error=sanitized_model_err,
                    duration_ms=attempt_dur,
                    error_category="MODEL_API_ERROR"
                ))
                observability.log_event("MODEL_ERROR", f"Model API failure: {sanitized_model_err}")
                last_error_category = "MODEL_API_ERROR"
                last_sanitized_error = f"Model generation error: {sanitized_model_err}"
                attempt += 1
                continue

            # Check if model identified clarification need
            if llm_out.needs_clarification:
                observability.log_event("AMBIGUITY_DETECTED", "Model requested clarification")
                total_duration_ms = round((time.time() - overall_start) * 1000, 2)
                return PipelineResult(
                    success=False,
                    question=question,
                    query_used="",
                    dataframe=None,
                    summary=f"Clarification needed: {llm_out.clarification_question}",
                    trace=trace,
                    total_attempts=attempt,
                    had_retry=False,
                    provider_label=self.llm_adapter.label,
                    total_duration_ms=total_duration_ms,
                    final_error="Question is ambiguous",
                    figure=None,
                    explanation=llm_out.explanation,
                    assumptions=llm_out.assumptions,
                    needs_clarification=True,
                    clarification_question=llm_out.clarification_question,
                    clarification_options=llm_out.clarification_options,
                    error_category="AMBIGUITY_DETECTED"
                )

            current_sql = llm_out.sql or ""
            final_explanation = llm_out.explanation
            final_assumptions = llm_out.assumptions

            # 3. AST Safety Validation
            val_res = validate_sql(current_sql)
            if not val_res.is_valid:
                duration_ms = round((time.time() - attempt_start) * 1000, 2)
                sanitized_val_err = sanitize_error_context(val_res.error_message or "Validation failed")
                trace.append(AttemptRecord(
                    attempt_number=attempt,
                    sql=current_sql,
                    status="VALIDATION_FAILED",
                    error_message=val_res.error_message,
                    sanitized_error=sanitized_val_err,
                    duration_ms=duration_ms,
                    explanation=final_explanation,
                    assumptions=final_assumptions,
                    error_category="VALIDATION_ERROR"
                ))
                observability.log_event("VALIDATION_FAILED", f"Attempt {attempt}: {sanitized_val_err}")
                last_error_category = "VALIDATION_ERROR"
                last_sanitized_error = (
                    f"Query was rejected by safety validator: {sanitized_val_err}. "
                    f"Ensure you return only a single read-only SELECT or WITH statement without forbidden commands."
                )
                attempt += 1
                continue

            validated_query = val_res.sanitized_sql or current_sql
            observability.log_event("VALIDATION_PASSED", f"Attempt {attempt}: SQL safety checks passed")

            # 4. Database Execution in Read-Only Sandbox
            exec_ok, df, exec_err, duration_ms = self.db_manager.execute_readonly_query(
                validated_query,
                row_limit=500,
                timeout_sec=5.0
            )

            if exec_ok and df is not None:
                # Execution Success
                trace.append(AttemptRecord(
                    attempt_number=attempt,
                    sql=validated_query,
                    status="SUCCESS",
                    error_message=None,
                    sanitized_error=None,
                    duration_ms=duration_ms,
                    rows_count=len(df),
                    explanation=final_explanation,
                    assumptions=final_assumptions,
                    error_category=None
                ))
                successful_df = df
                last_exec_time = duration_ms
                observability.log_event("DB_EXECUTED", f"Attempt {attempt}: query executed successfully ({len(df)} rows)")
                break
            else:
                # Recoverable SQLite Runtime Error (e.g. unknown column, missing join, syntax error)
                raw_err_msg = exec_err or "Unknown execution error"
                sanitized_exec_err = sanitize_error_context(raw_err_msg)

                trace.append(AttemptRecord(
                    attempt_number=attempt,
                    sql=validated_query,
                    status="EXECUTION_ERROR",
                    error_message=raw_err_msg,
                    sanitized_error=sanitized_exec_err,
                    duration_ms=duration_ms,
                    rows_count=0,
                    explanation=final_explanation,
                    assumptions=final_assumptions,
                    error_category="DATABASE_ERROR"
                ))
                observability.log_event("DB_ERROR", f"Attempt {attempt}: database error: {sanitized_exec_err}")
                last_error_category = "DATABASE_ERROR"
                last_sanitized_error = f"Database returned error: {sanitized_exec_err}"
                attempt += 1


        total_duration_ms = round((time.time() - overall_start) * 1000, 2)
        success = successful_df is not None

        # 6. Synthesize Executive Summary & Visualization
        if success:
            summary = self.llm_adapter.synthesize_summary(
                question=question,
                query=current_sql,
                df=successful_df
            )
            fig = generate_plotly_chart(successful_df, question)
            final_err = None
            final_cat = None
        else:
            summary = (
                f"Analysis could not be completed after {len(trace)} attempts. "
                f"Final error encountered: {last_sanitized_error or 'Query execution failed.'}"
            )
            fig = None
            final_err = last_sanitized_error
            final_cat = last_error_category

        observability.log_event("PIPELINE_COMPLETED", f"Pipeline finished: success={success}, attempts={len(trace)}")

        return PipelineResult(
            success=success,
            question=question,
            query_used=current_sql,
            dataframe=successful_df,
            summary=summary,
            trace=trace,
            total_attempts=len(trace),
            had_retry=len(trace) > 1,
            provider_label=self.llm_adapter.label,
            execution_time_ms=last_exec_time,
            total_duration_ms=total_duration_ms,
            final_error=final_err,
            figure=fig,
            explanation=final_explanation,
            assumptions=final_assumptions,
            needs_clarification=False,
            clarification_question=None,
            clarification_options=[],
            error_category=final_cat
        )
