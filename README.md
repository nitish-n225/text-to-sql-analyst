# ⚡ Text-to-SQL Analyst AI (Stage 4: Multi-Domain Database & Conversational Analytics)

An autonomous, safety-first **Text-to-SQL Analyst** application equipped with **Multi-Turn Conversational Analytics**, **Context Management**, **AST Safety Enforcement**, **Bounded Self-Correction Retries**, and **Multi-Domain Database Support**.

The system features two production-ready application stacks:
1. **Interactive Streamlit Analyst Dashboard (`app.py`)**: Multi-turn dialogue, context refinement chips, delta-explanation cards, schema inspection, and Plotly visualizations.
2. **FastAPI REST Engine + Responsive Web Application (`backend/` & `frontend/`)**: High-performance asynchronous API with real-time database schema reflection, self-healing retries, and a modern single-page dashboard.

---

## 🎯 Stage 4 Features & System Architecture

### Feature 1: Multi-Turn Conversational Analytics (`src/conversation.py`)
1. **Context-Aware Dialogue Management**:
   - Maintains an in-memory chronological history of user turns (`ConversationTurn`), tracking user questions, generated SQL, execution metrics, and delta explanations.
   - Prevents prompt bloating by automatically bounding prompt context to the most recent successful turns (default: 3).
2. **Conversational Follow-Up Resolution & Delta Explanations**:
   - Supports natural follow-up queries that reference previous results:
     - **Limit Adjustments**: e.g., *"Show only top 3 of those"* -> updates `LIMIT` to 3.
     - **Sort Inversions**: e.g., *"Show lowest instead"* -> switches `DESC` to `ASC`.
     - **Aggregations & Counts**: e.g., *"How many total records?"* -> wraps query in `COUNT(*)`.
     - **Column Projections**: e.g., *"Show their email addresses"* -> joins and projects contact fields.
   - Generates a clear `delta_explanation` detailing exactly how the prior query was adapted to fulfill the follow-up intent.
3. **Data Source Isolation Rule**:
   - Switching between datasets (e.g., from Sample Business DB to an uploaded CSV or SQLite file) immediately flushes active conversation history, preventing table or column hallucinations across unrelated schemas.
4. **Conversational Ambiguity Handling (`src/schema_context.py`)**:
   - Distinguishes between vague initial questions and valid conversational follow-ups. Words like *"those"*, *"top 3"*, or *"lowest"* are recognized as context modifiers rather than ambiguous inputs when prior turns exist.

---

### Feature 2: Multi-Domain Relational Databases (`backend/seed_data.py`)
Pre-seeded with realistic, relational SQLite databases across three commercial domains:
- **E-Commerce & Retail (`ecommerce.db`)**: 50 customers, 20 products, 166 orders, and 273 line items.
- **Company HR & Analytics (`company_hr.db`)**: 6 departments, 30 employees, and active projects with budget allocations.
- **Hospital & Healthcare (`healthcare.db`)**: 10 doctors across specializations, 40 patients, and 60 clinical appointments with diagnoses and prescription tracking.

---

### Feature 3: AST Safety Sandboxing & Bounded Self-Healing
1. **sqlglot AST Validator (`src/validator.py`)**:
   - Strict read-only enforcement: only single `SELECT` or `WITH ... SELECT` statements are permitted.
   - Hard blocks on destructive keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `ATTACH`, `PRAGMA`).
   - Re-validates every self-healed query generated during retry attempts.
2. **Database-Level Protection (`src/database.py` & `backend/db_manager.py`)**:
   - SQLite read-only connection URI (`mode=ro`) and `PRAGMA query_only = ON`.
   - Hard row limit caps (default: 500 rows) and execution timeouts (default: 5.0 seconds).
3. **Self-Healing Error Feedback Loop**:
   - When SQLite reports an error (e.g. unknown column, missing join), the error message is sanitized and fed back into the model for up to 2 correction attempts.

---

## 🚀 Quickstart Guide (Windows PowerShell)

### Step 1: Open Terminal in Project Directory
```powershell
cd "c:\Users\NITISH I D\Downloads\New folder (5)"
```

### Step 2: (Optional) Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Seed Sample Databases
```powershell
python backend/seed_data.py
```

### Step 5: Run the Complete Automated Test Suite (64 Tests)
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 💻 Running the Applications

### Option A: Launch Streamlit Analyst Dashboard
```powershell
streamlit run app.py
```
- Open `http://localhost:8501` in your browser.
- Enjoy interactive conversational querying, follow-up chips, Plotly visualizations, CSV downloads, and retry trace inspection.

### Option B: Launch FastAPI Backend & Modern Web UI
```powershell
python backend/main.py
```
or via Uvicorn:
```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
- Open `http://localhost:8000` in your browser to access the responsive web dashboard.
- Access interactive OpenAPI documentation at `http://localhost:8000/docs`.

---

## ⚙️ Configuration (Live LLM Mode)

To enable live Google Gemini or OpenAI language models:
1. Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Configure your API keys:
   ```env
   # Google Gemini
   GEMINI_API_KEY=AIzaSy...
   GEMINI_MODEL=gemini-1.5-flash

   # OpenAI
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-4o-mini
   ```
3. Restart the application. If no API keys are configured, both stacks seamlessly fall back to deterministic **Smart Demo / Offline Mode**.

---

## 🧪 Testing Coverage (64 Passing Tests)

The test suite consists of 64 unit and integration tests across 8 test suites:
- `tests/test_stage4_conversation.py` (11 tests):
  - Conversation turn records, session hygiene, bounded history pruning.
  - Data source isolation on dataset switch.
  - Conversational follow-ups (LIMIT adjustment, sort order reversal, count aggregation, filter refinement).
  - Multi-session registry in `ConversationManager`.
  - End-to-end multi-turn pipeline execution.
- `tests/test_backend_api.py` (12 tests):
  - Database selection, schema inspection, sample prompts.
  - Natural language querying across `ecommerce.db`, `company_hr.db`, and `healthcare.db`.
  - Self-healing retry trace verification.
  - Raw SQL read-only validation and destructive mutation blocking.
  - Query plan explanation (`EXPLAIN QUERY PLAN`).
  - Static frontend serving.
- `tests/test_stage3_uploads.py` (7 tests):
  - CSV and SQLite database uploads, sanitization, schema reflection, and ephemeral lifecycle cleanup.
- `tests/test_stage2_advanced.py` (10 tests):
  - Multi-table JOINs, aggregations, date arithmetic, ambiguity detection, and retry re-validation.
- `tests/test_validator.py` (12 tests):
  - AST safety checks, forbidden SQL blocking, multi-statement rejection.
- `tests/test_database.py` (5 tests):
  - SQLite read-only enforcement (`PRAGMA query_only = ON`) and schema summaries.
- `tests/test_demo_mode.py` (2 tests):
  - Deterministic offline demo mode compliance.
- `tests/test_pipeline.py` (5 tests):
  - Bounded retries, error sanitization, and pipeline trace recording.

---

## 📂 Project Structure

```
New folder (5)/
├── app.py                           # Streamlit analytics dashboard (Stage 4)
├── requirements.txt                 # Project dependencies
├── .env.example                     # Environment secrets template
├── README.md                        # Documentation
├── data/                            # Multi-domain SQLite databases
│   ├── business.db                  # Synthetic business database
│   ├── ecommerce.db                 # E-commerce store database
│   ├── company_hr.db                # HR & analytics database
│   └── healthcare.db                # Healthcare & hospital database
├── backend/                         # FastAPI backend architecture
│   ├── main.py                      # FastAPI app & REST endpoints
│   ├── db_manager.py                # Database connection & schema inspection
│   ├── sql_agent.py                 # Autonomous text-to-SQL engine with self-healing
│   └── seed_data.py                 # Multi-domain dataset seeding script
├── frontend/                        # Responsive web dashboard
│   ├── index.html                   # Modern UI layout
│   ├── styles.css                   # Responsive theme & glassmorphic styling
│   └── app.js                       # Frontend client & Chart.js integration
├── src/                             # Core Python analyst engine
│   ├── __init__.py                  # Public exports
│   ├── conversation.py              # Stage 4: Multi-turn session & context manager
│   ├── pipeline.py                  # Self-healing execution pipeline
│   ├── llm_adapter.py               # Adapters (DemoMode, Gemini, OpenAI) with delta logic
│   ├── schema_context.py            # Dynamic schema context & ambiguity detection
│   ├── validator.py                 # AST safety validator (sqlglot)
│   ├── upload_handler.py            # CSV & SQLite upload handlers
│   ├── database.py                  # SQLite database manager & sandboxing
│   ├── models.py                    # SQLAlchemy ORM models
│   ├── seeder.py                    # Sample database seeder
│   └── logger.py                    # Observability logging with secrets redaction
└── tests/                           # 64 Automated Unit & Integration Tests
    ├── test_stage4_conversation.py  # Conversational analytics tests (11 tests)
    ├── test_backend_api.py          # FastAPI endpoints & multi-domain tests (12 tests)
    ├── test_stage3_uploads.py       # File uploads & sanitization (7 tests)
    ├── test_stage2_advanced.py      # Joins, dates, ambiguity, retries (10 tests)
    ├── test_validator.py            # SQL AST validation (12 tests)
    ├── test_database.py             # Database sandboxing (5 tests)
    ├── test_demo_mode.py            # Offline demo mode (2 tests)
    └── test_pipeline.py             # Pipeline retries & error handling (5 tests)
```
