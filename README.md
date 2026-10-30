# ⚡ Text-to-SQL Analyst AI (Stage 2: Advanced Intelligence & Self-Correction)

An autonomous, safety-first **Text-to-SQL Analyst** application built in Python using **Streamlit**, **SQLite**, **SQLAlchemy**, **pandas**, **Plotly**, and **sqlglot**.

Ask analytical business questions in plain English. The AI translates questions into valid SQLite queries against your live database schema, validates safety gates, executes queries in a read-only sandbox, auto-corrects recoverable errors through a bounded self-healing retry loop (at most 2 retries), and renders an executive summary, structured explanations, assumptions, interactive Plotly visualizations, and data tables.

---

## 🎯 Stage 2 Features & Guarantees

1. **Schema-Aware Question Understanding (`src/schema_context.py`)**:
   - Discovers tables, columns, data types, primary keys, and foreign keys.
   - Extracts low-cardinality exact values (e.g. `loyalty_tier`: Bronze, Silver, Gold, Platinum; `status`: Delivered, Shipped, Processing, Cancelled, Refunded) and date ranges to prevent hallucinated values.
   - Discovers multi-table JOIN paths across all four tables (`customers` -> `orders` -> `order_items` -> `products`).
   - Socratic Ambiguity Detection: When questions are underspecified (e.g. "show best", "sales"), presents a clarification dialog with candidate interpretations.
2. **Structured LLM Output & Semantic Validation**:
   - Model outputs structured JSON containing:
     - `sql`: The generated SQLite statement.
     - `explanation`: Plain-English breakdown of query logic.
     - `assumptions`: Key analytical assumptions made.
     - `needs_clarification`: Boolean flag for ambiguous questions.
   - **Semantic Schema Validation**: Verifies referenced tables and columns exist in the actual database schema before database execution.
3. **Multi-Provider LLM Architecture**:
   - **Clearly Labeled Demo Mode (Default)**: Zero configuration required. Deterministic, verified SQL generation for complex analytical inquiries. Never claims an external LLM was called.
   - **Google Gemini (Live Mode)**: Dynamic schema ingestion and query generation via `gemini-1.5-flash` or `gemini-1.5-pro`.
   - **OpenAI (Live Mode)**: Live generation via `gpt-4o-mini` or `gpt-4o`.
   - **Strict Secrets Policy**: API keys are read *only* from environment variables (`.env`). No keys or secrets are ever exposed in logs, responses, or the user interface.
4. **AST SQL Parser & Safety Validation (`src/validator.py`)**:
   - **Single statement enforcement**: Semicolon-separated multi-statement injections are blocked.
   - **Read-only whitelist**: Only single read-only `SELECT` or safe read-only `WITH ... SELECT` CTE statements are permitted.
   - **Destructive operations strictly blocked**: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `PRAGMA`, `ATTACH`, `DETACH`, `VACUUM`, and administrative functions are rejected prior to execution.
5. **Read-Only Database Sandbox (`src/database.py`)**:
   - Executed through SQLite read-only URI mode (`file:...db?mode=ro`).
   - Enforced SQLite pragma: `PRAGMA query_only = ON;`.
   - Bounded row limits (default 500 rows) and execution timeouts (5.0s).
   - Prompt injection defense: User questions and database rows cannot override system instructions or safety rules.
6. **Bounded Self-Healing Correction Loop (`src/pipeline.py`)**:
   - If a query encounters a recoverable syntax, column mismatch, or execution error, the system triggers **at most two retries** (max 3 attempts total).
   - Database error messages are sanitized (stripping file system paths, line numbers, memory addresses, and internal traces) before being fed back to the LLM.
   - Every retry is re-validated through the safety validator before reaching the database.
7. **Observability, Diagnostics & User Experience (`src/logger.py` & `app.py`)**:
   - Structured diagnostic logger tracking pipeline events with automatic redaction of API keys and local paths.
   - Error categorization distinguishing `VALIDATION_ERROR`, `DATABASE_ERROR`, `MODEL_API_ERROR`, and `AMBIGUITY_DETECTED`.
   - Natural language executive summary, query explanation, and key assumptions.
   - Auto-detected Plotly charts (bar charts, time-series lines, and doughnut charts).
   - Searchable, exportable result table with CSV download and database schema inspector.

---

## 🚀 Quickstart Guide (Windows PowerShell)

### Step 1: Open Terminal in Project Directory
Open **Windows PowerShell** in this project folder:
```powershell
cd "c:\Users\NITISH I D\Downloads\New folder (5)"
```

### Step 2: (Optional) Create & Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Run Automated Tests
Verify all 34 unit tests across validator, database, demo mode, schema builder, and bounded retry pipeline:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### Step 5: Launch Streamlit Application
```powershell
streamlit run app.py
```
The application will open in your default browser at `http://localhost:8501`.

---

## ⚙️ Configuration (Live LLM Mode)

To run with real LLM providers instead of Demo Mode:

1. Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` in any text editor and paste your API key(s):
   ```env
   # Google Gemini
   GEMINI_API_KEY=AIzaSy...
   GEMINI_MODEL=gemini-1.5-flash

   # OpenAI
   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-4o-mini
   ```
3. Restart or reload the Streamlit app. The sidebar will detect your environment variable and allow switching to Live Mode.

> **Note on Demo Mode:** If no API keys are configured, the app operates automatically in **Demo Mode**.

---

## 🧪 Testing Coverage (34 Unit Tests)

The automated test suite in `tests/` covers:
- `test_validator.py` (12 tests): Safe `SELECT`/`WITH` queries, blocked write operations (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`), blocked multi-statements, and blocked pragmas.
- `test_database.py` (5 tests): Schema tables verification, record counts, and database-level read-only constraint verification (`PRAGMA query_only = ON`).
- `test_demo_mode.py` (2 tests): Deterministic demo queries, schema prompt generation, and disclosure compliance.
- `test_pipeline.py` (5 tests): Error sanitization, bounded self-healing retries, revalidation of retried queries, and max retry boundaries.
- `test_stage2_advanced.py` (10 tests):
  - Multi-table JOINs across all 4 tables (`customers` -> `orders` -> `order_items` -> `products`).
  - Aggregations (`SUM`, `COUNT`), date filters (`strftime`), and `HAVING` clauses.
  - Semantic schema validation detecting hallucinated tables and columns.
  - Socratic ambiguity detection and clarification options.
  - Strict revalidation of retried queries.
  - Maximum retry boundary (3 attempts max).
  - Destructive SQL blocked during correction retries.
  - 100% offline demo mode operation.
  - Structured output fields (`explanation`, `assumptions`).
  - Diagnostic logging and secrets redaction.

Run all tests anytime with:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 📂 Project Architecture

```
New folder (5)/
├── app.py                           # Streamlit analytics dashboard (Stage 2)
├── requirements.txt                 # Project dependencies
├── .env.example                     # Template for environment secrets
├── .gitignore                       # Git ignore rules
├── README.md                        # Project documentation
├── src/
│   ├── __init__.py                  # Package exports
│   ├── models.py                    # SQLAlchemy models (customers, products, orders, order_items)
│   ├── database.py                  # SQLite read-only connection, schema inspection, timeout management
│   ├── seeder.py                    # Synthetic business dataset generator
│   ├── schema_context.py            # Rich schema context, join guides, semantic validation & ambiguity
│   ├── validator.py                 # Robust SQL AST validator using sqlglot
│   ├── llm_adapter.py               # Configurable structured adapters (DemoMode, Gemini, OpenAI)
│   ├── logger.py                    # Diagnostic observability logger with secrets redaction
│   └── pipeline.py                  # Execution pipeline with bounded self-healing retry loop
└── tests/
    ├── __init__.py
    ├── test_validator.py            # Tests for SQL safety gates and forbidden operations (12 tests)
    ├── test_database.py             # Tests for DB schema, records, and read-only mode (5 tests)
    ├── test_demo_mode.py            # Tests for deterministic demo queries (2 tests)
    ├── test_pipeline.py             # Tests for bounded retries, error sanitization, and revalidation (5 tests)
    └── test_stage2_advanced.py      # Stage 2 advanced tests for joins, dates, ambiguity, etc. (10 tests)
```
