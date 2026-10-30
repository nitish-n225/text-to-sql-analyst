"""
Unit tests for DemoModeAdapter:
- Verifies deterministic queries for business questions
- Verifies Demo Mode disclosure label (never claims real LLM was used)
- Verifies queries pass SQL validation and execute cleanly against the database
"""

import unittest
from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.validator import validate_sql
from src.llm_adapter import DemoModeAdapter

class TestDemoMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager()
        seed_sample_database(cls.db, reset=False)
        cls.adapter = DemoModeAdapter()

    def test_demo_mode_adapter_properties(self):
        self.assertTrue(self.adapter.is_demo)
        self.assertEqual(self.adapter.provider_name, "demo")
        self.assertIn("Demo Mode", self.adapter.label)
        self.assertIn("No External LLM", self.adapter.label)

    def test_demo_mode_deterministic_queries(self):
        schema_prompt = self.db.get_schema_prompt_string()

        test_questions = [
            "Show top 5 customers by total spending",
            "What are product counts and average prices by category?",
            "Show order counts and total revenue grouped by order status",
            "What are the highest rated products?",
            "Show customer distribution by loyalty tier",
            "Which shipping cities generated highest sales volume?"
        ]

        for q in test_questions:
            sql = self.adapter.generate_sql(q, schema_prompt=schema_prompt)
            self.assertIsInstance(sql, str)
            self.assertGreater(len(sql), 10)

            # Validate SQL via AST validator
            val_res = validate_sql(sql)
            self.assertTrue(val_res.is_valid, f"Demo query for '{q}' failed validation: {val_res.error_message}")

            # Execute query on real database
            ok, df, err, ms = self.db.execute_readonly_query(sql)
            self.assertTrue(ok, f"Demo query for '{q}' failed execution: {err}")
            self.assertIsNotNone(df)
            self.assertGreater(len(df), 0)

            # Check summary synthesis
            summary = self.adapter.synthesize_summary(q, sql, df)
            self.assertIn("Demo Mode Summary", summary)
            self.assertTrue(str(len(df)) in summary or "Found" in summary)

if __name__ == "__main__":
    unittest.main()
