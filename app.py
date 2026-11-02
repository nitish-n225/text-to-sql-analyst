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
            if isinstance(sec_val, str):
                cleaned_val = sec_val.strip().strip("'\"")
                upper_key = sec_key.upper()
                os.environ[upper_key] = cleaned_val
                os.environ[sec_key] = cleaned_val
                if upper_key in ("GOOGLE_API_KEY", "GEMINI_KEY", "GOOGLE_KEY", "GEMINI", "GOOGLE"):
                    os.environ["GEMINI_API_KEY"] = cleaned_val
                elif upper_key in ("OPENAI", "OPENAI_KEY"):
                    os.environ["OPENAI_API_KEY"] = cleaned_val
            elif hasattr(sec_val, "items"):
                for sub_k, sub_v in sec_val.items():
                    if isinstance(sub_v, str):
                        cleaned_v = sub_v.strip().strip("'\"")
                        composite_key = f"{sec_key}_{sub_k}".upper()
                        os.environ[composite_key] = cleaned_v
                        if sub_k.upper() in ("API_KEY", "KEY"):
                            os.environ[f"{sec_key.upper()}_API_KEY"] = cleaned_v
                        if sec_key.lower() in ("gemini", "google") and sub_k.lower() in ("api_key", "key", "secret", "token"):
                            os.environ["GEMINI_API_KEY"] = cleaned_v
                        if sec_key.lower() == "openai" and sub_k.lower() in ("api_key", "key", "secret", "token"):
                            os.environ["OPENAI_API_KEY"] = cleaned_v
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
from src.upload_handler import (
    validate_file_upload,
    create_temp_db_from_csv,
    create_temp_db_from_sqlite,
    cleanup_temp_database,
    MAX_UPLOAD_SIZE_BYTES
)

# Streamlit Page Setup
st.set_page_config(
    page_title="Text-to-SQL Analyst AI | Stage 4",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State
if "sample_db_manager" not in st.session_state:
    st.session_state.sample_db_manager = seed_sample_database(reset=False)

if "db_manager" not in st.session_state:
    st.session_state.db_manager = st.session_state.sample_db_manager

if "temp_db_manager" not in st.session_state:
    st.session_state.temp_db_manager = None

if "data_source_mode" not in st.session_state:
    st.session_state.data_source_mode = "sample"

if "uploaded_source_name" not in st.session_state:
    st.session_state.uploaded_source_name = "business.db"

if "last_uploaded_key" not in st.session_state:
    st.session_state.last_uploaded_key = None

if "active_question" not in st.session_state:
    st.session_state.active_question = "Show top 5 customers by total spending and order count"

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "conversation_session" not in st.session_state:
    from src.conversation import ConversationSession
    st.session_state.conversation_session = ConversationSession(data_source="sample:business.db")

# Custom CSS for high-contrast, polished dashboard
st.markdown("""
<style>
    .delta-card {
        background: rgba(14, 165, 233, 0.15);
        border: 1px solid rgba(14, 165, 233, 0.45);
        border-radius: 10px;
        padding: 12px 18px;
        margin-bottom: 1.2rem;
        color: #38bdf8;
        font-size: 0.92rem;
    }
    .delta-title {
        font-weight: 700;
        display: block;
        margin-bottom: 4px;
        color: #7dd3fc;
    }
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

    # Automatically promote to Gemini if key available, else OpenAI, else Demo
    if "user_selected_provider" not in st.session_state:
        if providers_info["gemini"]["available"]:
            st.session_state.user_selected_provider = "gemini"
        elif providers_info["openai"]["available"]:
            st.session_state.user_selected_provider = "openai"
        else:
            st.session_state.user_selected_provider = "demo"
    elif not providers_info[st.session_state.user_selected_provider]["available"] and st.session_state.user_selected_provider != "demo":
        st.session_state.user_selected_provider = "gemini" if providers_info["gemini"]["available"] else "demo"

    default_idx = provider_options.index(st.session_state.user_selected_provider) if st.session_state.user_selected_provider in provider_options else 0

    selected_provider_key = st.selectbox(
        "Select LLM Provider:",
        options=provider_options,
        format_func=lambda x: provider_labels[x],
        index=default_idx,
        key="llm_provider_selectbox"
    )
    st.session_state.user_selected_provider = selected_provider_key

    info = providers_info[selected_provider_key]

    # Display API Key status without exposing keys
    if selected_provider_key == "demo":
        st.info("ℹ️ **Demo Mode Active**: Zero configuration required. Returns deterministic analytical queries for business questions. No external LLM called.")
    else:
        env_var_name = info.get("env_var", "")
        if info["available"]:
            st.success(f"✅ Secret `{env_var_name}` detected. Live AI active.")
        else:
            st.warning(f"⚠️ `{env_var_name}` is not configured. Add it in Streamlit Cloud Settings &rarr; Secrets or connect below.")

    # In-Session Quick Connect expander (keys remain securely in memory only, never written to disk or committed)
    with st.expander("🔑 Quick Connect Gemini Key", expanded=(not providers_info["gemini"]["available"] and selected_provider_key == "gemini")):
        st.caption("Connect a Google Gemini API key for this browser session without configuring Streamlit Secrets. Key is held securely in memory only.")
        input_key = st.text_input(
            "Gemini API Key:",
            type="password",
            placeholder="AIzaSy...",
            key="gemini_session_key_input",
            help="Free-tier API key from Google AI Studio (aistudio.google.com)"
        )
        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            if st.button("Connect Key", key="btn_connect_gemini", use_container_width=True):
                if input_key and input_key.strip():
                    clean_k = input_key.strip().strip("'\"")
                    os.environ["GEMINI_API_KEY"] = clean_k
                    st.session_state.user_selected_provider = "gemini"
                    st.rerun()
                else:
                    st.error("Please enter a valid key.")
        with col_c2:
            if os.environ.get("GEMINI_API_KEY") and st.button("Disconnect", key="btn_disconnect_gemini", use_container_width=True):
                os.environ.pop("GEMINI_API_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)
                st.session_state.user_selected_provider = "demo"
                st.rerun()

    st.markdown("---")
    st.markdown("### 🛠️ Self-Healing Error Simulation")
    simulate_error = st.checkbox(
        "Test Self-Correction Retry Loop",
        value=False,
        help="Intentionally induces a column mismatch error on Attempt 1 to demonstrate error sanitization, AST revalidation, and automatic recovery on Attempt 2."
    )

    # ---------------------------------------------------------
    # Sidebar: Data Source Selection (Stage 3, Feature 1)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### 📁 Data Source Selection")
    
    source_options = ["sample", "csv", "sqlite"]
    source_labels = {
        "sample": "📊 Sample Business DB (Pre-seeded)",
        "csv": "📄 Upload CSV File (.csv)",
        "sqlite": "🗄️ Upload SQLite DB (.db, .sqlite)"
    }

    selected_source = st.radio(
        "Choose Data Source:",
        options=source_options,
        format_func=lambda x: source_labels[x],
        index=source_options.index(st.session_state.data_source_mode) if st.session_state.data_source_mode in source_options else 0,
        key="source_selector_radio"
    )

    if selected_source != st.session_state.data_source_mode:
        st.session_state.data_source_mode = selected_source
        if selected_source == "sample":
            cleanup_temp_database(st.session_state.temp_db_manager)
            st.session_state.temp_db_manager = None
            st.session_state.db_manager = st.session_state.sample_db_manager
            st.session_state.uploaded_source_name = "business.db"
            st.session_state.active_question = "Show top 5 customers by total spending and order count"
            st.session_state.last_uploaded_key = None
            st.rerun()

    # CSV Upload Handler
    if selected_source == "csv":
        uploaded_csv = st.file_uploader(
            "Upload CSV File (Max 25 MB):",
            type=["csv"],
            key="csv_file_uploader",
            help="Uploaded CSV is loaded into an ephemeral temporary SQLite database in memory."
        )
        if uploaded_csv is not None:
            upload_key = f"csv_{uploaded_csv.name}_{uploaded_csv.size}"
            if st.session_state.last_uploaded_key != upload_key:
                with st.spinner(f"Ingesting CSV '{uploaded_csv.name}' into sandbox..."):
                    ok, new_db, tbl_name, err = create_temp_db_from_csv(
                        uploaded_csv.name,
                        uploaded_csv.getvalue()
                    )
                    if not ok:
                        st.error(f"❌ Upload Failed: {err}")
                    else:
                        cleanup_temp_database(st.session_state.temp_db_manager)
                        st.session_state.temp_db_manager = new_db
                        st.session_state.db_manager = new_db
                        st.session_state.uploaded_source_name = f"{uploaded_csv.name} (table: `{tbl_name}`)"
                        st.session_state.last_uploaded_key = upload_key
                        st.session_state.active_question = f"Show top 10 records from {tbl_name}"
                        st.session_state.last_result = None
                        st.success(f"✅ Ingested `{uploaded_csv.name}` into table `{tbl_name}`!")
                        st.rerun()

    # SQLite Upload Handler
    elif selected_source == "sqlite":
        uploaded_sqlite = st.file_uploader(
            "Upload SQLite Database (Max 25 MB):",
            type=["db", "sqlite", "sqlite3"],
            key="sqlite_file_uploader",
            help="Upload an existing SQLite database. Tables and foreign keys will be reflected automatically."
        )
        if uploaded_sqlite is not None:
            upload_key = f"sqlite_{uploaded_sqlite.name}_{uploaded_sqlite.size}"
            if st.session_state.last_uploaded_key != upload_key:
                with st.spinner(f"Validating SQLite database '{uploaded_sqlite.name}'..."):
                    ok, new_db, err = create_temp_db_from_sqlite(
                        uploaded_sqlite.name,
                        uploaded_sqlite.getvalue()
                    )
                    if not ok:
                        st.error(f"❌ Upload Failed: {err}")
                    else:
                        cleanup_temp_database(st.session_state.temp_db_manager)
                        st.session_state.temp_db_manager = new_db
                        st.session_state.db_manager = new_db
                        st.session_state.uploaded_source_name = uploaded_sqlite.name
                        st.session_state.last_uploaded_key = upload_key
                        st.session_state.conversation_session.set_data_source(f"sqlite:{uploaded_sqlite.name}")
                        summary = new_db.get_schema_summary()
                        first_tbl = summary["tables"][0]["table_name"] if summary["tables"] else "data"
                        st.session_state.active_question = f"Show top 10 records from {first_tbl}"
                        st.session_state.last_result = None
                        st.success(f"✅ Verified SQLite database with {len(summary['tables'])} table(s)!")
                        st.rerun()

    # Active Database Schema & Stats
    st.markdown("---")
    st.markdown("### 📊 Active Database Schema")
    st.caption(f"Source: **{st.session_state.uploaded_source_name}**")
    db = st.session_state.db_manager
    schema_summary = db.get_schema_summary()
    
    col_a, col_b = st.columns(2)
    for i, tbl in enumerate(schema_summary["tables"]):
        target_col = col_a if i % 2 == 0 else col_b
        target_col.metric(tbl["table_name"][:14].title(), f"{tbl['row_count']} rows")

    with st.expander("🔍 Inspect Schema & Sample Records"):
        for tbl in schema_summary["tables"]:
            st.markdown(f"**Table: `{tbl['table_name']}`** (~{tbl['row_count']} rows)")
            cols_df = pd.DataFrame(tbl["columns"])[["name", "type", "primary_key", "nullable"]]
            st.dataframe(cols_df, use_container_width=True, hide_index=True)
            if tbl["sample_rows"]:
                st.caption(f"Sample records from `{tbl['table_name']}`:")
                st.dataframe(pd.DataFrame(tbl["sample_rows"]), use_container_width=True, hide_index=True)

    if st.session_state.data_source_mode == "sample":
        if st.button("🔄 Reset / Re-seed Database"):
            seed_sample_database(db, reset=True)
            st.success("Database re-seeded with fresh records!")
            st.rerun()
    else:
        if st.button("↩️ Switch Back to Sample Business DB"):
            cleanup_temp_database(st.session_state.temp_db_manager)
            st.session_state.temp_db_manager = None
            st.session_state.db_manager = st.session_state.sample_db_manager
            st.session_state.data_source_mode = "sample"
            st.session_state.uploaded_source_name = "business.db"
            st.session_state.conversation_session.set_data_source("sample:business.db")
            st.session_state.active_question = "Show top 5 customers by total spending and order count"
            st.session_state.last_uploaded_key = None
            st.rerun()

    # Multi-Turn Conversation Controls in Sidebar
    st.markdown("---")
    st.markdown("### 💬 Conversational Context")
    sess = st.session_state.conversation_session
    st.caption(f"Turns in Memory: **{sess.turn_count}** &bull; Dataset: `{st.session_state.uploaded_source_name}`")
    if sess.turn_count > 0:
        if st.button("🗑️ Clear Conversation History", use_container_width=True):
            sess.clear()
            st.session_state.last_result = None
            st.success("Conversation history cleared!")
            st.rerun()

        with st.expander("📜 Inspect Conversation Turns", expanded=False):
            for t in sess.get_history():
                st.markdown(f"**Turn {t.turn_id}:** {t.question}")
                if t.delta_explanation:
                    st.caption(f"⚡ {t.delta_explanation}")
                if t.sql:
                    st.code(t.sql, language="sql")
                if t.error_message:
                    st.caption(f"❌ Error: {t.error_message}")
                st.markdown("---")

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
st.markdown('<div class="sub-title">Stage 4: Multi-Domain Database &bull; Conversational Analytics &bull; AST Safety &bull; Bounded Self-Healing</div>', unsafe_allow_html=True)

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

# Dynamic Example Questions based on Active Dataset
st.markdown("##### 💡 Example Analytical Questions:")

if st.session_state.data_source_mode == "sample":
    sample_queries = [
        ("Top Spenders", "Show top 5 customers by total spending and order count"),
        ("Customer Purchases (4-Table JOIN)", "Show customer product purchase history with prices and dates"),
        ("Monthly Sales Trend", "Show monthly sales trends over time"),
        ("Repeat Buyers (HAVING)", "Show repeat frequent buyers with more than 3 orders"),
        ("Category Pricing", "What are the product counts and average prices by category?"),
        ("Order Status Revenue", "Show order counts and total revenue grouped by order status")
    ]
else:
    # Dynamically generate sample queries tailored to the uploaded table(s)
    curr_summary = st.session_state.db_manager.get_schema_summary()
    first_tbl_info = curr_summary["tables"][0] if curr_summary["tables"] else None
    sample_queries = []
    
    if first_tbl_info:
        tbl_n = first_tbl_info["table_name"]
        cols_list = [c["name"] for c in first_tbl_info["columns"]]
        num_cols = [
            c["name"] for c in first_tbl_info["columns"]
            if any(t in c.get("type", "").upper() for t in ["INT", "FLOAT", "REAL", "NUMERIC", "DECIMAL", "DOUBLE"])
            and not c["name"].lower().endswith("id")
        ]
        cat_cols = [c["name"] for c in first_tbl_info["columns"] if c["name"] not in num_cols and not c["name"].lower().endswith("id")]

        sample_queries.append(("Explore 10 Rows", f"Show top 10 records from {tbl_n}"))
        sample_queries.append(("Record Count", f"Count total records in {tbl_n}"))
        
        if num_cols:
            sample_queries.append((f"Top by {num_cols[0].title()}", f"Top 5 records by {num_cols[0]}"))
            sample_queries.append((f"Average {num_cols[0].title()}", f"What is the average {num_cols[0]} in {tbl_n}?"))
        
        if cat_cols and num_cols:
            sample_queries.append((f"Group by {cat_cols[0].title()}", f"Show total {num_cols[0]} grouped by {cat_cols[0]} in {tbl_n}"))
        elif cat_cols:
            sample_queries.append((f"Count by {cat_cols[0].title()}", f"Count records grouped by {cat_cols[0]} in {tbl_n}"))

if sample_queries:
    chip_cols = st.columns(len(sample_queries))
    for i, (label, sample_q) in enumerate(sample_queries):
        if chip_cols[i].button(label, key=f"chip_{i}"):
            st.session_state.active_question = sample_q
            st.rerun()

# Conversational Follow-Up Chips (when previous turn context exists)
sess = st.session_state.conversation_session
if sess.turn_count > 0:
    st.markdown("##### 💬 Suggested Follow-Up Refinements:")
    follow_up_chips = [
        ("Top 3 of those", "Show only top 3 of those"),
        ("Lowest instead", "Show lowest instead"),
        ("Count total", "How many total records?"),
        ("Platinum Tier", "Filter to only platinum loyalty tier"),
        ("Show Emails", "Show their email addresses")
    ]
    f_cols = st.columns(len(follow_up_chips))
    for i, (f_lbl, f_q) in enumerate(follow_up_chips):
        if f_cols[i].button(f_lbl, key=f"follow_chip_{i}"):
            st.session_state.active_question = f_q
            st.rerun()

# Question Input Bar
user_question = st.text_input(
    "Ask anything in plain English (or follow up on previous results):",
    value=st.session_state.active_question,
    placeholder="e.g., Show top 5 customers by total spending, or 'Show top 3 of those'",
    key="input_box"
)

col_run, col_clear = st.columns([1, 6])
run_clicked = col_run.button("🚀 Run Analysis", type="primary", use_container_width=True)

if run_clicked and user_question.strip():
    with st.spinner("Analyzing question, generating structured SQL, and validating through safety gates..."):
        pipeline = TextToSqlPipeline(
            db_manager=st.session_state.db_manager,
            llm_adapter=active_adapter,
            session=st.session_state.conversation_session
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

    # Conversational Follow-Up Delta Card
    if res.delta_explanation:
        turn_num = res.turn_id or st.session_state.conversation_session.turn_count
        st.markdown(f"""
        <div class="delta-card">
            <span class="delta-title">💬 Conversational Context Refinement Applied (Turn #{turn_num})</span>
            <div>{res.delta_explanation}</div>
        </div>
        """, unsafe_allow_html=True)

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
