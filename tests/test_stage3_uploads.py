"""
Automated Test Suite for Stage 3, Feature 1: Multi-Domain Database and CSV Upload.
Covers:
1. Valid CSV file upload, schema reflection, query generation, and execution.
2. Valid SQLite database upload, multi-table schema reflection, foreign key discovery, and query execution.
3. Invalid, empty, corrupted, and oversized file rejections without sensitive error leakage.
4. Safe identifier sanitization for tables and columns (reserved keywords, punctuation, deduplication).
5. AST SQL validator blocking destructive operations on uploaded datasets.
6. Read-only SQLite sandbox enforcement on uploaded databases.
7. Ephemeral temporary file lifecycle and cleanup.
8. Backward compatibility and regression checks with Stage 1 and 2 functionality.
"""

import os
import sqlite3
import tempfile
import unittest
import pandas as pd

from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.validator import validate_sql
from src.schema_context import SchemaContextBuilder
from src.llm_adapter import DemoModeAdapter, LLMOutput
from src.pipeline import TextToSqlPipeline
from src.upload_handler import (
    validate_file_upload,
    create_temp_db_from_csv,
    create_temp_db_from_sqlite,
    cleanup_temp_database,
    sanitize_table_name,
    sanitize_column_names,
    MAX_UPLOAD_SIZE_BYTES
)

class TestStage3Uploads(unittest.TestCase):

    def test_csv_upload_valid_data(self):
        """Tests uploading a clean CSV, schema reflection, query generation, and execution."""
        csv_content = (
            "department,employee_name,annual_salary,years_experience\n"
            "Engineering,Alice Smith,125000,6\n"
            "Engineering,Bob Jones,140000,8\n"
            "Marketing,Carol White,95000,4\n"
            "Finance,David Brown,110000,5\n"
            "Marketing,Emma Green,88000,3\n"
        ).encode("utf-8")

        ok, db_mgr, tbl_name, err = create_temp_db_from_csv("Company Salaries 2024.csv", csv_content)
        self.assertTrue(ok)
        self.assertIsNotNone(db_mgr)
        self.assertEqual(tbl_name, "company_salaries_2024")
        self.assertIsNone(err)

        try:
            # 1. Verify schema discovery
            summary = db_mgr.get_schema_summary()
            self.assertEqual(len(summary["tables"]), 1)
            tbl = summary["tables"][0]
            self.assertEqual(tbl["table_name"], "company_salaries_2024")
            self.assertEqual(tbl["row_count"], 5)

            col_names = [c["name"] for c in tbl["columns"]]
            self.assertIn("department", col_names)
            self.assertIn("annual_salary", col_names)
            self.assertIn("years_experience", col_names)

            # 2. Verify SchemaContextBuilder reflects this uploaded table
            schema_builder = SchemaContextBuilder(db_mgr)
            schema = schema_builder.get_full_schema(force_refresh=True)
            self.assertIn("company_salaries_2024", schema["tables"])
            prompt = schema_builder.build_llm_prompt_context()
            self.assertIn("company_salaries_2024", prompt)
            self.assertIn("SINGLE-TABLE", prompt)

            # 3. Test plain-English query generation via DemoModeAdapter
            adapter = DemoModeAdapter()
            pipeline = TextToSqlPipeline(db_mgr, adapter)

            # Query: Record count
            res_cnt = pipeline.run("How many records are in the dataset?")
            self.assertTrue(res_cnt.success)
            self.assertIn("total_records", res_cnt.dataframe.columns)
            self.assertEqual(res_cnt.dataframe.iloc[0]["total_records"], 5)

            # Query: Top by salary
            res_top = pipeline.run("Show top employees by annual salary")
            self.assertTrue(res_top.success)
            self.assertEqual(len(res_top.dataframe), 5)
            # Highest salary should be first (140,000)
            self.assertEqual(res_top.dataframe.iloc[0]["annual_salary"], 140000)

            # Query: Group by department
            res_grp = pipeline.run("Show annual salary grouped by department")
            self.assertTrue(res_grp.success)
            self.assertIn("department", res_grp.dataframe.columns)

        finally:
            cleanup_temp_database(db_mgr)

    def test_sqlite_upload_valid_database(self):
        """Tests uploading a valid multi-table SQLite database file."""
        # Create a temporary SQLite database in-memory and export bytes
        temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_path = temp_file.name
        temp_file.close()

        try:
            conn = sqlite3.connect(temp_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE clinics (
                    id INTEGER PRIMARY KEY,
                    clinic_name TEXT NOT NULL,
                    city TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE doctors (
                    id INTEGER PRIMARY KEY,
                    clinic_id INTEGER,
                    doctor_name TEXT NOT NULL,
                    specialty TEXT NOT NULL,
                    FOREIGN KEY (clinic_id) REFERENCES clinics(id)
                );
            """)
            cur.execute("INSERT INTO clinics VALUES (1, 'Downtown Health', 'Seattle'), (2, 'Uptown Care', 'Portland');")
            cur.execute("INSERT INTO doctors VALUES (101, 1, 'Dr. Adams', 'Cardiology'), (102, 2, 'Dr. Baker', 'Pediatrics');")
            conn.commit()
            conn.close()

            with open(temp_path, "rb") as f:
                db_bytes = f.read()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        ok, db_mgr, err = create_temp_db_from_sqlite("healthcare_network.sqlite", db_bytes)
        self.assertTrue(ok)
        self.assertIsNotNone(db_mgr)
        self.assertIsNone(err)

        try:
            summary = db_mgr.get_schema_summary()
            table_names = {t["table_name"] for t in summary["tables"]}
            self.assertIn("clinics", table_names)
            self.assertIn("doctors", table_names)

            # Verify foreign key discovery
            schema_builder = SchemaContextBuilder(db_mgr)
            schema = schema_builder.get_full_schema(force_refresh=True)
            self.assertEqual(len(schema["relationships"]), 1)
            self.assertEqual(schema["relationships"][0]["from_table"], "doctors")
            self.assertEqual(schema["relationships"][0]["to_table"], "clinics")

            # Execute query through sandbox
            adapter = DemoModeAdapter()
            pipeline = TextToSqlPipeline(db_mgr, adapter)
            res = pipeline.run("Show all records from clinics")
            self.assertTrue(res.success)
            self.assertEqual(len(res.dataframe), 2)

        finally:
            cleanup_temp_database(db_mgr)

    def test_invalid_and_corrupt_files_handling(self):
        """Tests that invalid, empty, oversized, and corrupt files are caught gracefully."""
        # 1. Empty file
        ok, err = validate_file_upload("test.csv", b"", "csv")
        self.assertFalse(ok)
        self.assertIn("empty", err.lower())

        # 2. Oversized file (> 25 MB)
        huge_bytes = b"0" * (MAX_UPLOAD_SIZE_BYTES + 1024)
        ok, err = validate_file_upload("huge.csv", huge_bytes, "csv")
        self.assertFalse(ok)
        self.assertIn("exceeds maximum", err.lower())

        # 3. Invalid file extension
        ok, err = validate_file_upload("payload.exe", b"fake binary data", "csv")
        self.assertFalse(ok)
        self.assertIn("invalid file format", err.lower())

        # 4. Corrupt SQLite file (wrong header)
        fake_db = b"NOT AN SQLITE FILE AT ALL 123456789"
        ok_db, db_mgr, err_db = create_temp_db_from_sqlite("corrupt.db", fake_db)
        self.assertFalse(ok_db)
        self.assertIsNone(db_mgr)
        self.assertIn("sqlite", err_db.lower())

        # 5. Empty CSV file without rows or columns
        empty_csv = b"   \n   \n"
        ok_c, c_mgr, tbl, c_err = create_temp_db_from_csv("empty.csv", empty_csv)
        self.assertFalse(ok_c)
        self.assertIsNone(c_mgr)
        self.assertIn("no data", c_err.lower())

        # 6. SQLite database with zero user tables
        zero_tbl_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        zero_tbl_path = zero_tbl_file.name
        zero_tbl_file.close()
        try:
            c = sqlite3.connect(zero_tbl_path)
            c.execute("PRAGMA user_version = 1;")
            c.commit()
            c.close()
            with open(zero_tbl_path, "rb") as f:
                zero_bytes = f.read()
        finally:
            if os.path.exists(zero_tbl_path):
                os.remove(zero_tbl_path)

        ok_zero, zero_mgr, zero_err = create_temp_db_from_sqlite("no_tables.db", zero_bytes)
        self.assertFalse(ok_zero)
        self.assertIsNone(zero_mgr)
        self.assertIn("user tables", zero_err.lower())

    def test_identifier_sanitization(self):
        """Tests that table and column names are properly cleaned and deduplicated."""
        # Table name sanitization
        self.assertEqual(sanitize_table_name("2024 Sales & Marketing (v1).csv"), "t_2024_sales_marketing_v1")
        self.assertEqual(sanitize_table_name("café-orders.csv"), "cafe_orders")
        self.assertEqual(sanitize_table_name("select.csv"), "select_data")
        self.assertEqual(sanitize_table_name(""), "uploaded_data")

        # Column name sanitization & deduplication
        raw_df = pd.DataFrame(columns=[
            "Employee ID",
            "Salary ($)",
            "First-Name",
            "Status %",
            "Duplicate Name",
            "Duplicate Name"
        ])
        clean_df = sanitize_column_names(raw_df)
        cols = list(clean_df.columns)

        self.assertEqual(cols[0], "employee_id")
        self.assertEqual(cols[1], "salary")
        self.assertEqual(cols[2], "first_name")
        self.assertEqual(cols[3], "status")
        self.assertEqual(cols[4], "duplicate_name")
        self.assertEqual(cols[5], "duplicate_name_1")

    def test_destructive_sql_blocked_on_uploaded_dataset(self):
        """Verifies that AST safety validator blocks destructive SQL on uploaded tables."""
        csv_content = b"item_id,price,stock\n1,10.5,50\n2,20.0,30\n"
        ok, db_mgr, tbl_name, _ = create_temp_db_from_csv("inventory.csv", csv_content)
        self.assertTrue(ok)

        try:
            # 1. AST Validator blocks DROP TABLE
            drop_res = validate_sql(f"DROP TABLE {tbl_name}")
            self.assertFalse(drop_res.is_valid)

            # 2. AST Validator blocks DELETE FROM
            del_res = validate_sql(f"DELETE FROM {tbl_name} WHERE item_id = 1")
            self.assertFalse(del_res.is_valid)

            # 3. AST Validator blocks UPDATE
            up_res = validate_sql(f"UPDATE {tbl_name} SET stock = 0")
            self.assertFalse(up_res.is_valid)

            # 4. AST Validator blocks INSERT INTO
            ins_res = validate_sql(f"INSERT INTO {tbl_name} VALUES (3, 30.0, 10)")
            self.assertFalse(ins_res.is_valid)

            # 5. AST Validator blocks multi-statement injection
            inject_res = validate_sql(f"SELECT * FROM {tbl_name}; DROP TABLE {tbl_name};")
            self.assertFalse(inject_res.is_valid)

            # 6. Database sandbox blocks writes even if attempted
            conn = db_mgr.get_readonly_connection()
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute(f"UPDATE {tbl_name} SET stock = 999 WHERE item_id = 1;")
            conn.close()

        finally:
            cleanup_temp_database(db_mgr)

    def test_temporary_storage_lifecycle_and_cleanup(self):
        """Verifies that temporary databases are safely removed on cleanup without disk leakage."""
        csv_content = b"col_a,col_b\n1,hello\n2,world\n"
        ok, db_mgr, _, _ = create_temp_db_from_csv("temp_sample.csv", csv_content)
        self.assertTrue(ok)
        temp_path = db_mgr.db_path
        self.assertTrue(os.path.exists(temp_path))

        # Cleanup
        cleanup_temp_database(db_mgr)
        self.assertFalse(os.path.exists(temp_path))

    def test_regression_existing_sample_db(self):
        """Ensures that default business database continues to function identically."""
        db = DatabaseManager()
        seed_sample_database(db, reset=False)
        schema_builder = SchemaContextBuilder(db)
        schema = schema_builder.get_full_schema(force_refresh=True)

        # Must contain all 4 standard tables
        self.assertIn("customers", schema["tables"])
        self.assertIn("orders", schema["tables"])
        self.assertIn("order_items", schema["tables"])
        self.assertIn("products", schema["tables"])

        # Must preserve relationships and join paths
        self.assertGreaterEqual(len(schema["relationships"]), 3)
        self.assertIn(("customers", "orders"), schema["join_paths"])

        # Run sample analytical query
        pipeline = TextToSqlPipeline(db, DemoModeAdapter())
        res = pipeline.run("Show top 5 customers by total spending and order count")
        self.assertTrue(res.success)
        self.assertEqual(len(res.dataframe), 5)


if __name__ == "__main__":
    unittest.main()
