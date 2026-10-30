"""
Unit tests for SQL AST validator (sqlglot).
Tests safe SELECT / WITH CTE queries and strictly blocks:
- Write operations (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE)
- Multi-statement injections (semicolon chaining)
- Dangerous pragmas and functions
"""

import unittest
from src.validator import validate_sql

class TestSqlValidator(unittest.TestCase):
    def test_safe_select_queries(self):
        valid_queries = [
            "SELECT id, name, email FROM customers;",
            "SELECT c.name, SUM(o.total_amount) FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name ORDER BY 2 DESC LIMIT 10",
            "SELECT * FROM products WHERE price > 50.0 AND rating >= 4.5",
            "SELECT status, COUNT(*), ROUND(AVG(total_amount), 2) FROM orders GROUP BY status",
            "WITH high_spenders AS (SELECT customer_id, SUM(total_amount) as spent FROM orders GROUP BY customer_id) SELECT * FROM high_spenders WHERE spent > 500"
        ]
        for q in valid_queries:
            res = validate_sql(q)
            self.assertTrue(res.is_valid, f"Expected valid query for '{q}', got error: {res.error_message}")
            self.assertIsNone(res.error_message)
            self.assertIsNotNone(res.sanitized_sql)

    def test_blocked_drop_table(self):
        res = validate_sql("DROP TABLE customers;")
        self.assertFalse(res.is_valid)
        self.assertTrue("Forbidden" in res.error_message or "blocked" in res.error_message)

    def test_blocked_delete_from(self):
        res = validate_sql("DELETE FROM products WHERE id = 1;")
        self.assertFalse(res.is_valid)
        self.assertTrue("Forbidden" in res.error_message or "blocked" in res.error_message)

    def test_blocked_update(self):
        res = validate_sql("UPDATE customers SET loyalty_tier = 'Gold' WHERE id = 1;")
        self.assertFalse(res.is_valid)
        self.assertTrue("Forbidden" in res.error_message or "blocked" in res.error_message)

    def test_blocked_insert_into(self):
        res = validate_sql("INSERT INTO products (name, category, price) VALUES ('Injected', 'Electronics', 10);")
        self.assertFalse(res.is_valid)
        self.assertTrue("Forbidden" in res.error_message or "blocked" in res.error_message)

    def test_blocked_alter_table(self):
        res = validate_sql("ALTER TABLE orders ADD COLUMN injected_col TEXT;")
        self.assertFalse(res.is_valid)
        self.assertTrue("Forbidden" in res.error_message or "blocked" in res.error_message)

    def test_blocked_truncate_table(self):
        res = validate_sql("TRUNCATE TABLE order_items;")
        self.assertFalse(res.is_valid)

    def test_blocked_multiple_statements(self):
        multi_statements = [
            "SELECT * FROM customers; DROP TABLE orders;",
            "SELECT 1; SELECT 2;",
            "SELECT name FROM products; DELETE FROM customers WHERE 1=1;",
            "SELECT id FROM orders; VACUUM;"
        ]
        for q in multi_statements:
            res = validate_sql(q)
            self.assertFalse(res.is_valid, f"Expected rejection for multi-statement query: {q}")
            self.assertTrue("Multiple statements" in res.error_message or "blocked" in res.error_message)

    def test_blocked_pragma_commands(self):
        res = validate_sql("PRAGMA table_info(customers);")
        self.assertFalse(res.is_valid)
        self.assertTrue("blocked" in res.error_message or "Forbidden" in res.error_message)

    def test_blocked_attach_database(self):
        res = validate_sql("ATTACH DATABASE 'malicious.db' AS evil;")
        self.assertFalse(res.is_valid)

    def test_blocked_dangerous_functions(self):
        res = validate_sql("SELECT load_extension('malicious.dll');")
        self.assertFalse(res.is_valid)
        self.assertTrue("load_extension" in res.error_message or "blocked" in res.error_message)

    def test_empty_query(self):
        res = validate_sql("   ")
        self.assertFalse(res.is_valid)
        self.assertIn("Empty query", res.error_message)

if __name__ == "__main__":
    unittest.main()
