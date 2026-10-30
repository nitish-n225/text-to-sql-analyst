"""
Streamlit Web Application: Text-to-SQL Analyst AI (Stage 2).
Provides:
- Natural-language question interface with ambiguity clarification
- Clearly labeled Demo Mode (offline deterministic) and Live Mode (Gemini / OpenAI)
- Rigorous SQL AST validation and read-only database execution
- Bounded self-healing correction retry trace (max 2 retries) with error categorization
- Structured explanations, assumptions, executive summary, Plotly visualization, and data table
- Diagnostic observability logs with automatic secrets redaction
"""

import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Sync Streamlit Cloud secrets into environment if deployed on share.streamlit.io
try:
    if hasattr(st, "secrets"):
        for sec_key, sec_val in st.secrets.items():
            if isinstance(sec_val, str) and sec_key not in os.environ:
                os.environ[sec_key] = sec_val
except Exception:
    pass

from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.llm_adapter import (
    get_available_providers,
    create_llm_adapter,
    DemoModeAdapter,
    GeminiAdapter,
    OpenAIAdapter
)
from src.pipeline import TextToSqlPipeline, PipelineResult
from src.logger import observability

# Streamlit Page Setup
st.set_page_config(
    page_title="Text-to-SQL Analyst AI | Stage 2",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State
if "db_manager" not in st.session_state:
    st.session_state.db_manager = seed_sample_database(reset=False)

if "active_question" not in st.session_state:
    st.session_state.active_question = "Show top 5 customers by total spending and order count"

if "last_result" not in st.session_state:
    st.session_state.last_result = None

# Custom CSS for high-contrast, polished dashboard
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 0.2rem;
        background: linear-gradient(135deg, #6366f1 0%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    .status-card-demo {
        background: rgba(99, 102, 241, 0.12);
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 1rem;
        color: #cbd5e1;
        font-size: 0.88rem;
    }
    .status-card-live {
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.35);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 1rem;
        color: #a7f3d0;
        font-size: 0.88rem;
    }
    .clarification-card {
        background: rgba(245, 158, 11, 0.12);
        border: 1px solid rgba(245, 158, 11, 0.4);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 1.5rem;
    }
    .clarification-title {
        color: #f59e0b;
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .retry-box-fail {
        background: rgba(244, 63, 94, 0.1);
        border-left: 4px solid #f43f5e;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 8px;
        font-size: 0.85rem;
    }
    .retry-box-succ {
        background: rgba(16, 185, 129, 0.1);
        border-left: 4px solid #10b981;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 8px;
        font-size: 0.85rem;
    }
    .badge-validation {
        background: rgba(244, 63, 94, 0.2);
        color: #f43f5e;
        border: 1px solid rgba(244, 63, 94, 0.4);
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .badge-database {
        background: rgba(245, 158, 11, 0.2);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.4);
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Sidebar: Engine Configuration & Database Inspection
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚡ AI Engine Configuration")
    
    providers_info = get_available_providers()
    provider_options = ["demo", "gemini", "openai"]
    provider_labels = {
        "demo": "Demo Mode (Deterministic Offline)",
        "gemini": "Google Gemini (Live Mode)",
        "openai": "OpenAI (Live Mode)"
    }

    selected_provider_key = st.selectbox(
        "Select LLM Provider:",
        options=provider_options,
        format_func=lambda x: provider_labels[x],
        index=0
    )

    info = providers_info[selected_provider_key]

    # Display API Key status without exposing keys
    if selected_provider_key == "demo":
        st.info("ℹ️ **Demo Mode Active**: Zero configuration required. Returns deterministic analytical queries for business questions. No external LLM called.")
    else:
        env_var_name = info.get("env_var", "")
        if info["available"]:
            st.success(f"✅ Environment secret `{env_var_name}` detected. Live mode ready.")
        else:
            st.warning(f"⚠️ `{env_var_name}` is not set in environment or `.env`. Falling back to Demo Mode.")

    st.markdown("---")
    st.markdown("### 🛠️ Self-Healing Error Simulation")
    simulate_error = st.checkbox(
        "Test Self-Correction Retry Loop",
        value=False,
        help="Intentionally induces a column mismatch error on Attempt 1 to demonstrate error sanitization, AST revalidation, and automatic recovery on Attempt 2."
    )

    st.markdown("---")
    st.markdown("### 📊 Business Database")
    db = st.session_state.db_manager
    schema_summary = db.get_schema_summary()
    
    col_a, col_b = st.columns(2)
    for i, tbl in enumerate(schema_summary["tables"]):
        target_col = col_a if i % 2 == 0 else col_b
        target_col.metric(tbl["table_name"].title(), f"{tbl['row_count']} rows")

    with st.expander("🔍 Inspect Database Schema"):
        for tbl in schema_summary["tables"]:
            st.markdown(f"**Table: `{tbl['table_name']}`**")
            cols_df = pd.DataFrame(tbl["columns"])[["name", "type", "primary_key", "nullable"]]
            st.dataframe(cols_df, use_container_width=True, hide_index=True)
            if tbl["sample_rows"]:
                st.caption("Sample Records:")
                st.dataframe(pd.DataFrame(tbl["sample_rows"]), use_container_width=True, hide_index=True)

    if st.button("🔄 Reset / Re-seed Database"):
        seed_sample_database(db, reset=True)
        st.success("Database re-seeded with fresh records!")
        st.rerun()

    with st.expander("📝 Observability & Diagnostic Logs"):
        events = observability.get_events(limit=25)
        if not events:
            st.caption("No events recorded yet.")
        else:
            for ev in reversed(events):
                st.text(f"[{ev.timestamp}] {ev.event_type}\n{ev.message}")

# ---------------------------------------------------------
# Main Panel: Natural Language Analyst
# ---------------------------------------------------------
st.markdown('<div class="main-title">Text-to-SQL Analyst AI</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Stage 2: Schema-Aware Intelligence &bull; Structured Explanations &bull; Ambiguity Clarification &bull; Bounded Self-Healing</div>', unsafe_allow_html=True)

# Provider status badge
if selected_provider_key == "demo" or not providers_info[selected_provider_key]["available"]:
    st.markdown("""
    <div class="status-card-demo">
        <strong>🏷️ CLEARLY LABELED DEMO MODE:</strong> Operating in deterministic offline mode. Pre-configured domain queries are validated and executed safely against SQLite. No external LLM API is invoked.
    </div>
    """, unsafe_allow_html=True)
    active_adapter = DemoModeAdapter()
else:
    st.markdown(f"""
    <div class="status-card-live">
        <strong>🟢 LIVE LLM MODE ACTIVE:</strong> Connected to <strong>{provider_labels[selected_provider_key]}</strong>. Real database schema is dynamically supplied for natural-language query translation.
    </div>
    """, unsafe_allow_html=True)
    active_adapter = create_llm_adapter(selected_provider_key)

# Sample Query Chips (including Stage 2 multi-table and date filter queries)
st.markdown("##### 💡 Example Analytical Questions:")
sample_queries = [
    ("Top Spenders", "Show top 5 customers by total spending and order count"),
    ("Customer Purchases (4-Table JOIN)", "Show customer product purchase history with prices and dates"),
    ("Monthly Sales Trend", "Show monthly sales trends over time"),
    ("Repeat Buyers (HAVING)", "Show repeat frequent buyers with more than 3 orders"),
    ("Category Pricing", "What are the product counts and average prices by category?"),
    ("Order Status Revenue", "Show order counts and total revenue grouped by order status")
]

chip_cols = st.columns(len(sample_queries))
for i, (label, sample_q) in enumerate(sample_queries):
    if chip_cols[i].button(label, key=f"chip_{i}"):
        st.session_state.active_question = sample_q

# Question Input Bar
user_question = st.text_input(
    "Ask anything in plain English:",
    value=st.session_state.active_question,
    placeholder="e.g., Show top 5 customers by total spending",
    key="input_box"
)

col_run, col_clear = st.columns([1, 6])
run_clicked = col_run.button("🚀 Run Analysis", type="primary", use_container_width=True)

if run_clicked and user_question.strip():
    with st.spinner("Analyzing question, generating structured SQL, and validating through safety gates..."):
        pipeline = TextToSqlPipeline(
            db_manager=st.session_state.db_manager,
            llm_adapter=active_adapter
        )
        result: PipelineResult = pipeline.run(
            question=user_question.strip(),
            induce_error_first_attempt=simulate_error
        )
        st.session_state.last_result = result

# ---------------------------------------------------------
# Display Analysis Results
# ---------------------------------------------------------
if st.session_state.last_result:
    res: PipelineResult = st.session_state.last_result

    st.markdown("---")

    # Ambiguity Clarification Handling
    if res.needs_clarification:
        st.markdown(f"""
        <div class="clarification-card">
            <div class="clarification-title">💬 Clarification Needed</div>
            <div>{res.clarification_question}</div>
        </div>
        """, unsafe_allow_html=True)
        if res.clarification_options:
            st.markdown("**Suggested specific options:**")
            opt_cols = st.columns(min(len(res.clarification_options), 4))
            for idx, opt in enumerate(res.clarification_options):
                target_c = opt_cols[idx % len(opt_cols)]
                if target_c.button(opt, key=f"clar_opt_{idx}"):
                    st.session_state.active_question = opt
                    st.rerun()

    # Self-Healing & Retry Trace Card
    st.markdown("### 🔄 Execution & Self-Healing Trace")
    
    if res.had_retry and res.success:
        st.warning(f"⚡ **Self-Correction Activated**: The initial query encountered a database error. The sanitized error context was fed back to the engine, and the query self-healed successfully on Attempt {res.total_attempts}!")
    elif res.success:
        st.success(f"✅ **Single-Pass Success**: Validated and executed cleanly on Attempt 1 ({res.execution_time_ms} ms).")
    elif not res.needs_clarification:
        error_badge = f"<span class='badge-validation'>VALIDATION ERROR</span>" if res.error_category == "VALIDATION_ERROR" else f"<span class='badge-database'>DATABASE ERROR</span>"
        st.error(f"❌ **Execution Failed**: Max retries (2) exceeded. Error: {res.final_error}")

    if res.trace:
        with st.expander(f"Inspect Retry Trace ({res.total_attempts} attempts recorded)", expanded=res.had_retry):
            for rec in res.trace:
                badge = f"<span class='badge-validation'>{rec.error_category}</span>" if rec.error_category == "VALIDATION_ERROR" else (f"<span class='badge-database'>{rec.error_category}</span>" if rec.error_category else "")
                if rec.status == "SUCCESS":
                    st.markdown(f"""
                    <div class="retry-box-succ">
                        <strong>Attempt {rec.attempt_number}: SUCCESS</strong> &bull; {rec.duration_ms} ms &bull; {rec.rows_count} rows returned<br/>
                        <code>{rec.sql}</code>
                    </div>
                    """, unsafe_allow_html=True)
                elif rec.status == "VALIDATION_FAILED":
                    st.markdown(f"""
                    <div class="retry-box-fail">
                        <strong>Attempt {rec.attempt_number}: REJECTED BY AST VALIDATOR {badge}</strong> &bull; {rec.duration_ms} ms<br/>
                        <code>{rec.sql}</code><br/>
                        <em>Reason: {rec.sanitized_error}</em><br/>
                        <small>🛡️ Query was blocked before reaching the database. Sanitized feedback passed for retry.</small>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="retry-box-fail">
                        <strong>Attempt {rec.attempt_number}: DATABASE EXECUTION ERROR {badge}</strong> &bull; {rec.duration_ms} ms<br/>
                        <code>{rec.sql}</code><br/>
                        <em>Database Error: {rec.sanitized_error}</em><br/>
                        <small>🔄 Sanitized error context fed back to LLM for bounded correction retry.</small>
                    </div>
                    """, unsafe_allow_html=True)

    if res.success and res.dataframe is not None:
        # Structured Explanation & Assumptions
        if res.explanation or res.assumptions:
            col_exp, col_ass = st.columns([3, 2])
            with col_exp:
                st.markdown("##### 💡 Query Logic & Explanation")
                st.write(res.explanation)
            with col_ass:
                if res.assumptions:
                    st.markdown("##### 📌 Key Assumptions")
                    for a in res.assumptions:
                        st.markdown(f"- {a}")

        # Executive Summary
        st.markdown("### 📋 Executive Summary")
        st.info(res.summary)

        # SQL Query Used
        st.markdown("### 💻 SQL Query Used")
        st.code(res.query_used, language="sql")

        # Interactive Plotly Visualization & Data Grid
        tab_viz, tab_data = st.tabs(["📊 Data Visualization", "📑 Result Table"])

        with tab_viz:
            if res.figure:
                st.plotly_chart(res.figure, use_container_width=True)
            else:
                st.markdown("*Data shape is best inspected in tabular format.*")

        with tab_data:
            st.dataframe(res.dataframe, use_container_width=True)
            csv_data = res.dataframe.to_csv(index=False)
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv_data,
                file_name="sql_analyst_results.csv",
                mime="text/csv"
            )

        # Security & Safety Footnote
        st.caption(
            f"🔒 **Safety Enforced**: Executed via SQLite Read-Only connection (PRAGMA query_only = ON) "
            f"&bull; AST-validated via sqlglot &bull; Row limit: 500 &bull; Timeout: 5.0s &bull; Execution time: {res.execution_time_ms} ms"
        )
