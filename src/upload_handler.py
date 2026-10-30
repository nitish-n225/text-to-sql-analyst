"""
Upload Handler for Multi-Domain Database and CSV Upload (Stage 3, Feature 1).
Provides:
1. Strict file type and size validation (max 25 MB).
2. Malformed file detection and graceful error handling.
3. Safe identifier sanitization for tables and columns.
4. Ephemeral temporary database creation compatible with Streamlit Community Cloud.
5. Automatic cleanup of temporary storage without leaking disk space.
"""

import os
import re
import io
import atexit
import sqlite3
import tempfile
import unicodedata
from typing import Tuple, Optional, List, Dict, Any, Set
import pandas as pd
from sqlalchemy import create_engine
from src.database import DatabaseManager
from src.logger import observability

MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024 # 25 MB limit
ALLOWED_CSV_EXTENSIONS = {".csv"}
ALLOWED_SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
SQLITE_MAGIC_HEADER = b"SQLite format 3\x00"

# Registry of active temporary database files for guaranteed cleanup
_ACTIVE_TEMP_FILES: Set[str] = set()

def _cleanup_all_registered_temp_files():
    """Cleanup handler registered with atexit to purge temporary files on exit."""
    for path in list(_ACTIVE_TEMP_FILES):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    _ACTIVE_TEMP_FILES.clear()

atexit.register(_cleanup_all_registered_temp_files)


def sanitize_table_name(filename: str, fallback: str = "uploaded_data") -> str:
    """
    Sanitizes a file name into a clean, safe SQLite table identifier:
    - Strips file extension.
    - Converts unicode to ascii equivalent.
    - Replaces non-alphanumeric characters with underscores.
    - Ensures the name does not start with a digit.
    - Truncates to at most 60 characters.
    """
    if not filename or not filename.strip():
        return fallback

    # Strip extension
    base = filename.rsplit(".", 1)[0].strip()
    
    # Normalize unicode (e.g. café -> cafe)
    normalized = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    
    # Replace non-alphanumeric with underscore
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    
    # Prevent leading digit (invalid in standard SQL identifier without quoting)
    if clean and clean[0].isdigit():
        clean = f"t_{clean}"
        
    # Check reserved SQLite keywords
    sqlite_reserved = {"select", "table", "order", "group", "from", "where", "user", "index", "values", "check"}
    if clean in sqlite_reserved:
        clean = f"{clean}_data"

    if not clean:
        return fallback

    return clean[:60]


def sanitize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes DataFrame column names to ensure valid, safe SQLite identifiers:
    - Strips whitespace.
    - Converts to lowercase.
    - Replaces spaces, dashes, and punctuation with underscores.
    - Removes currency symbols and parenthesis.
    - Deduplicates identical column names.
    """
    clean_cols: List[str] = []
    seen: Dict[str, int] = {}

    for i, raw_col in enumerate(df.columns):
        raw_str = str(raw_col).strip()
        # Remove currency symbols and punctuation
        no_sym = re.sub(r"[\$€£¥₹%#@!&*()\[\]{}:;,\?\/\\|<>=+`~]", "", raw_str)
        # Normalize to ascii
        norm = unicodedata.normalize("NFKD", no_sym).encode("ascii", "ignore").decode("ascii")
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", norm).strip("_").lower()

        if not clean or clean[0].isdigit():
            clean = f"col_{clean}" if clean else f"col_{i+1}"

        # Deduplicate
        if clean in seen:
            seen[clean] += 1
            final_name = f"{clean}_{seen[clean]}"
        else:
            seen[clean] = 0
            final_name = clean

        clean_cols.append(final_name)

    df_clean = df.copy()
    df_clean.columns = clean_cols
    return df_clean


def validate_file_upload(file_name: str, file_bytes: bytes, file_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validates uploaded file size, extension, and content headers:
    
    Returns:
        (is_valid: bool, error_message: Optional[str])
    """
    if not file_bytes or len(file_bytes) == 0:
        return False, "The uploaded file is empty (0 bytes)."

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        return False, f"File exceeds maximum permitted size of {max_mb} MB. Please upload a smaller file."

    ext = os.path.splitext(file_name)[1].lower()

    if file_type.lower() == "csv":
        if ext not in ALLOWED_CSV_EXTENSIONS:
            return False, f"Invalid file format '{ext}'. Only CSV (.csv) files are permitted for CSV upload."
    elif file_type.lower() in ("sqlite", "db"):
        if ext not in ALLOWED_SQLITE_EXTENSIONS:
            return False, f"Invalid file format '{ext}'. Only SQLite (.db, .sqlite, .sqlite3) files are permitted."
        # Validate magic header
        if len(file_bytes) < 16 or file_bytes[:16] != SQLITE_MAGIC_HEADER:
            return False, "Invalid SQLite database file: The file does not have a valid SQLite 3 header or is corrupted."
    else:
        return False, f"Unsupported upload type: {file_type}."

    return True, None


def create_temp_db_from_csv(
    file_name: str,
    file_bytes: bytes
) -> Tuple[bool, Optional[DatabaseManager], Optional[str], Optional[str]]:
    """
    Parses an uploaded CSV file, loads it into an ephemeral SQLite database in temporary storage,
    and returns a ready-to-use DatabaseManager.
    
    Returns:
        (success: bool, db_manager: Optional[DatabaseManager], table_name: Optional[str], error_msg: Optional[str])
    """
    is_valid, val_err = validate_file_upload(file_name, file_bytes, file_type="csv")
    if not is_valid:
        return False, None, None, val_err

    # Try reading CSV with common encodings
    df: Optional[pd.DataFrame] = None
    encodings_to_try = ["utf-8", "latin1", "cp1252", "utf-8-sig"]
    last_err = ""

    for enc in encodings_to_try:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
            break
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            return False, None, None, "The uploaded CSV file contains no data or headers."
        except pd.errors.ParserError as pe:
            last_err = f"CSV parsing error: {str(pe).splitlines()[0]}"
            break
        except Exception as e:
            last_err = f"Malformed CSV file: {str(e)}"
            break

    if df is None:
        return False, None, None, last_err or "Failed to decode CSV file with standard text encodings."

    if df.empty or len(df.columns) == 0:
        return False, None, None, "The uploaded CSV file contains no data rows or columns."

    # Sanitize table and column names
    table_name = sanitize_table_name(file_name)
    df_clean = sanitize_column_names(df)

    # Create temporary SQLite database
    try:
        temp_file = tempfile.NamedTemporaryFile(
            prefix=f"text2sql_{table_name}_",
            suffix=".db",
            delete=False
        )
        temp_db_path = temp_file.name
        temp_file.close()

        _ACTIVE_TEMP_FILES.add(temp_db_path)

        # Ingest dataframe into SQLite
        rw_engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
        df_clean.to_sql(table_name, rw_engine, if_exists="replace", index=False)
        rw_engine.dispose()

        # Wrap in DatabaseManager
        db_mgr = DatabaseManager(temp_db_path)
        observability.log_event(
            "CSV_UPLOADED",
            f"Uploaded CSV '{file_name}' imported as table '{table_name}' ({len(df_clean)} rows, {len(df_clean.columns)} cols)"
        )
        return True, db_mgr, table_name, None

    except Exception as e:
        return False, None, None, f"Failed to initialize database from CSV: {str(e)}"


def create_temp_db_from_sqlite(
    file_name: str,
    file_bytes: bytes
) -> Tuple[bool, Optional[DatabaseManager], Optional[str]]:
    """
    Validates and writes an uploaded SQLite database file to ephemeral temporary storage,
    checks database integrity, and returns a ready-to-use DatabaseManager.
    
    Returns:
        (success: bool, db_manager: Optional[DatabaseManager], error_msg: Optional[str])
    """
    is_valid, val_err = validate_file_upload(file_name, file_bytes, file_type="sqlite")
    if not is_valid:
        return False, None, val_err

    temp_db_path = None
    try:
        temp_file = tempfile.NamedTemporaryFile(
            prefix="text2sql_sqlite_",
            suffix=".db",
            delete=False
        )
        temp_file.write(file_bytes)
        temp_file.flush()
        temp_db_path = temp_file.name
        temp_file.close()

        _ACTIVE_TEMP_FILES.add(temp_db_path)

        # Verify SQLite integrity
        conn = sqlite3.connect(f"file:{temp_db_path}?mode=ro", uri=True, timeout=5.0)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check(1);")
        integrity_row = cur.fetchone()
        if not integrity_row or integrity_row[0] != "ok":
            conn.close()
            cleanup_temp_database_file(temp_db_path)
            return False, None, "Corrupted SQLite database: Integrity check failed."

        # Verify it has at least one user table
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tbl_count = cur.fetchone()[0]
        conn.close()

        if tbl_count == 0:
            cleanup_temp_database_file(temp_db_path)
            return False, None, "The uploaded SQLite database does not contain any user tables."

        db_mgr = DatabaseManager(temp_db_path)
        observability.log_event(
            "SQLITE_UPLOADED",
            f"Uploaded SQLite database '{file_name}' verified ({tbl_count} tables)"
        )
        return True, db_mgr, None

    except sqlite3.DatabaseError as de:
        if temp_db_path:
            cleanup_temp_database_file(temp_db_path)
        return False, None, f"SQLite format error: {str(de)}"
    except Exception as e:
        if temp_db_path:
            cleanup_temp_database_file(temp_db_path)
        return False, None, f"Failed to initialize SQLite database: {str(e)}"


def cleanup_temp_database_file(db_path: Optional[str]):
    """Safely removes a temporary SQLite file and its journals from disk."""
    if not db_path:
        return

    # Remove from active tracking
    if db_path in _ACTIVE_TEMP_FILES:
        _ACTIVE_TEMP_FILES.discard(db_path)

    # Clean up main DB file and possible WAL/journal companions
    for companion in [db_path, f"{db_path}-wal", f"{db_path}-shm", f"{db_path}-journal"]:
        try:
            if os.path.exists(companion):
                os.remove(companion)
        except Exception:
            pass


def cleanup_temp_database(db_manager: Optional[DatabaseManager]):
    """Disposes engine connections and deletes temp DB file if temporary."""
    if not db_manager:
        return
    try:
        if hasattr(db_manager, "rw_engine") and db_manager.rw_engine:
            db_manager.rw_engine.dispose()
    except Exception:
        pass

    db_path = getattr(db_manager, "db_path", None)
    # Only clean up files that are in temporary directory or registered
    if db_path and (db_path in _ACTIVE_TEMP_FILES or "text2sql_" in os.path.basename(db_path)):
        cleanup_temp_database_file(db_path)
