"""
Unit tests for DatabaseManager and seeder:
- Schema verification (customers, products, orders, order_items)
- Read-only connection enforcement (blocking modifications at database level)
- Timeout & row limit enforcement
"""

import os
import sqlite3
import unittest
from src.database import DatabaseManager
from src.seeder import seed_sample_database

class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_path = os.path.join(os.path.dirname(__file__), "test_business.db")
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)
        cls.test_db = DatabaseManager(db_path=cls.test_db_path)
        seed_sample_database(cls.test_db, reset=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def test_database_tables_and_records(self):
        summary = self.test_db.get_schema_summary()
        table_names = [tbl["table_name"] for tbl in summary["tables"]]

        self.assertIn("customers", table_names)
        self.assertIn("products", table_names)
        self.assertIn("orders", table_names)
        self.assertIn("order_items", table_names)

        counts = {tbl["table_name"]: tbl["row_count"] for tbl in summary["tables"]}
        self.assertGreaterEqual(counts["customers"], 40)
        self.assertGreaterEqual(counts["products"], 20)
        self.assertGreaterEqual(counts["orders"], 50)
        self.assertGreaterEqual(counts["order_items"], 100)

    def test_readonly_connection_blocks_mutations(self):
        """
        Verifies that the read-only connection strictly prevents database writes
        via PRAGMA query_only=ON and URI mode=ro.
        """
        conn = self.test_db.get_readonly_connection()
        try:
            with self.assertRaises(sqlite3.OperationalError) as ctx:
                conn.execute(
                    "INSERT INTO customers (name, email, country, signup_date, loyalty_tier) "
                    "VALUES ('Hack', 'hack@test.com', 'US', '2024-01-01', 'Gold')"
                )
            err_msg = str(ctx.exception).lower()
            self.assertTrue("readonly" in err_msg or "read-only" in err_msg)
        finally:
            conn.close()


    def test_readonly_query_execution_success(self):
        ok, df, err, ms = self.test_db.execute_readonly_query("SELECT id, name, price FROM products LIMIT 5")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 5)
        self.assertIn("name", df.columns)
        self.assertGreaterEqual(ms, 0.0)

    def test_readonly_query_row_limit(self):
        ok, df, err, ms = self.test_db.execute_readonly_query("SELECT * FROM customers", row_limit=10)
        self.assertTrue(ok)
        self.assertEqual(len(df), 10)

    def test_schema_prompt_generation(self):
        prompt_str = self.test_db.get_schema_prompt_string()
        self.assertIn("CREATE TABLE customers", prompt_str)
        self.assertIn("CREATE TABLE products", prompt_str)
        self.assertIn("CREATE TABLE orders", prompt_str)
        self.assertIn("CREATE TABLE order_items", prompt_str)
        self.assertIn("FOREIGN KEY", prompt_str)

if __name__ == "__main__":
    unittest.main()
