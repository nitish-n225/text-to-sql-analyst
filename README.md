# ⚡ Text-to-SQL Analyst AI (Stage 3: Multi-Domain Database & CSV Upload)

An autonomous, safety-first **Text-to-SQL Analyst** application built in Python using **Streamlit**, **SQLite**, **SQLAlchemy**, **pandas**, **Plotly**, and **sqlglot**.

Ask analytical business questions in plain English. The AI translates questions into valid SQLite queries against your live database schema, validates safety gates, executes queries in a read-only sandbox, auto-corrects recoverable errors through a bounded self-healing retry loop (at most 2 retries), and renders an executive summary, structured explanations, assumptions, interactive Plotly visualizations, and data tables.

---

## 🎯 Stage 3 Features & Guarantees

### Feature 1: Multi-Domain Database & CSV Upload (`src/upload_handler.py`)
1. **Three Selectable Data Sources**:
   - **Sample Business Database (Default)**: Pre-seeded eCommerce database with 4 relational tables (`customers`, `orders`, `order_items`, `products`).
   - **Upload Custom CSV (`.csv`)**: Converts any uploaded CSV file into a temporary in-memory/ephemeral SQLite table. Automatically sanitizes table and column names to ensure valid SQL identifiers.
   - **Upload Custom SQLite Database (`.db`, `.sqlite`, `.sqlite3`)**: Validates the SQLite 3 magic header, runs integrity checks, inspects all user tables, and reflects foreign key relationships dynamically.
2. **Ephemeral Cloud Storage (Streamlit Cloud Compatible)**:
   - Uses temporary storage (`tempfile`) with automatic resource disposal and disk cleanup.
   - No reliance on persistent disk storage across cloud container restarts.
   - Immediate cleanup when switching data sources or closing sessions.
3. **Rigorous File Validation & Error Sanitization**:
   - Strictly validates extensions and binary magic headers (`SQLite format 3\000`).
   - Caps upload size at 25 MB.
   - Catches corrupted, empty, or unparseable files with clean user feedback, preventing sensitive path or stack trace leakage in logs and UI.
4. **Dynamic Schema-Aware Natural Language Querying**:
   - Automatically reflects table names, column names, data types, primary keys, and foreign keys for uploaded datasets.
   - In **Demo Mode (Offline)**: Intelligently formulates exploratory queries, aggregations, counts, and top-N rankings against uploaded tables without external LLM calls.
   - In **Live Mode (Gemini / OpenAI)**: Supplies complete schema context, data types, and sample records to the model.
5. **Universal AST Safety Gates & Read-Only Sandboxing**:
   - All queries on uploaded datasets are strictly enforced through AST validation (`sqlglot`).
   - Only single read-only `SELECT` and safe `WITH ... SELECT` queries are allowed.
   - Destructive commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `ATTACH`, `PRAGMA`) are blocked before database execution.
   - SQLite read-only connection URI (`mode=ro`) and `PRAGMA query_only = ON` provide defense-in-depth.

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
Verify all 41 unit tests across upload handling, validator, database sandboxing, schema builder, demo mode, and bounded retries:
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

## 🧪 Testing Coverage (41 Unit Tests)

The automated test suite in `tests/` covers:
- `test_stage3_uploads.py` (7 tests):
  - Valid CSV file upload, schema reflection, query generation, and execution.
  - Multi-table SQLite database upload, table and foreign key discovery.
  - Invalid, empty, oversized (>25 MB), and corrupted file rejections.
  - Table and column identifier sanitization (reserved keywords, punctuation, deduplication).
  - Destructive SQL blocked on uploaded datasets via AST validator and database sandbox.
  - Ephemeral temporary file lifecycle and cleanup without disk leakage.
  - Regression testing verifying sample business database functionality remains intact.
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
├── app.py                           # Streamlit analytics dashboard (Stage 3)
├── requirements.txt                 # Project dependencies
├── .env.example                     # Template for environment secrets
├── .gitignore                       # Git ignore rules
├── README.md                        # Project documentation
├── src/
│   ├── __init__.py                  # Package exports
│   ├── upload_handler.py            # Stage 3: CSV & SQLite validation, ingestion, and temp cleanup
│   ├── models.py                    # SQLAlchemy models (customers, products, orders, order_items)
│   ├── database.py                  # SQLite read-only connection, schema inspection, timeout management
│   ├── seeder.py                    # Synthetic business dataset generator
│   ├── schema_context.py            # Dynamic schema context, join guides, semantic validation & ambiguity
│   ├── validator.py                 # Robust SQL AST validator using sqlglot
│   ├── llm_adapter.py               # Configurable structured adapters (DemoMode, Gemini, OpenAI)
│   ├── logger.py                    # Diagnostic observability logger with secrets redaction
│   └── pipeline.py                  # Execution pipeline with bounded self-healing retry loop
└── tests/
    ├── __init__.py
    ├── test_stage3_uploads.py       # Stage 3: CSV/SQLite uploads, validation, sanitization & lifecycle (7 tests)
    ├── test_stage2_advanced.py      # Stage 2: Joins, dates, ambiguity, retry revalidation (10 tests)
    ├── test_validator.py            # SQL safety gates and forbidden operations (12 tests)
    ├── test_database.py             # DB schema, records, and read-only mode (5 tests)
    ├── test_demo_mode.py            # Deterministic demo queries (2 tests)
    └── test_pipeline.py             # Bounded retries, error sanitization, and revalidation (5 tests)
```

