"""
Unit tests for TextToSqlPipeline:
- Bounded correction retries (at most 2 retries, total 3 attempts)
- Error sanitization (stripping local paths and internal system details)
- Strict revalidation of every retry before execution
"""

import unittest
import pandas as pd
from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.pipeline import TextToSqlPipeline, sanitize_error_context, MAX_CORRECTION_RETRIES
from src.llm_adapter import BaseLLMAdapter, DemoModeAdapter

class DestructiveRetryMockAdapter(BaseLLMAdapter):
    """Mock adapter that attempts a destructive query on retry."""
    def __init__(self):
        self.call_count = 0

    def generate_sql(self, question: str, schema_prompt: str, error_feedback: str = None) -> str:
        self.call_count += 1
        if self.call_count == 1:
            # Syntax/column error on attempt 1
            return "SELECT non_existent_col FROM customers"
        elif self.call_count == 2:
            # Malicious query on retry
            return "DROP TABLE customers;"
        return "SELECT id FROM customers"

    def synthesize_summary(self, question: str, query: str, df: pd.DataFrame) -> str:
        return "Summary"

class AlwaysFailingMockAdapter(BaseLLMAdapter):
    def generate_sql(self, question: str, schema_prompt: str, error_feedback: str = None) -> str:
        return "SELECT broken_column FROM non_existent_table"

    def synthesize_summary(self, question: str, query: str, df: pd.DataFrame) -> str:
        return "Fail"

class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager()
        seed_sample_database(cls.db, reset=False)

    def test_error_sanitization(self):
        raw_win_err = r"SQLite Operational Error: no such table: client in C:\Users\Alice\AppData\Local\Temp\business.db at 0x7ffd9b"
        sanitized = sanitize_error_context(raw_win_err)
        self.assertNotIn(r"C:\Users\Alice", sanitized)
        self.assertNotIn("0x7ffd9b", sanitized)
        self.assertIn("no such table: client", sanitized)

        raw_unix_err = "sqlite3.OperationalError: no such column: rev at /var/data/app/business.db"
        sanitized_unix = sanitize_error_context(raw_unix_err)
        self.assertNotIn("/var/data", sanitized_unix)
        self.assertIn("no such column: rev", sanitized_unix)

    def test_pipeline_single_attempt_success(self):
        pipeline = TextToSqlPipeline(self.db, DemoModeAdapter())
        result = pipeline.run("Show top 5 customers by total spending", induce_error_first_attempt=False)

        self.assertTrue(result.success)
        self.assertEqual(result.total_attempts, 1)
        self.assertFalse(result.had_retry)
        self.assertIsNotNone(result.dataframe)
        self.assertEqual(len(result.dataframe), 5)
        self.assertEqual(len(result.trace), 1)
        self.assertEqual(result.trace[0].status, "SUCCESS")

    def test_pipeline_bounded_retry_self_healing(self):
        pipeline = TextToSqlPipeline(self.db, DemoModeAdapter())
        # Induces error on attempt 1, self-heals on attempt 2
        result = pipeline.run("Show top 5 customers by total spending", induce_error_first_attempt=True)

        self.assertTrue(result.success)
        self.assertEqual(result.total_attempts, 2)
        self.assertTrue(result.had_retry)
        self.assertEqual(len(result.trace), 2)
        self.assertEqual(result.trace[0].status, "EXECUTION_ERROR")
        self.assertIn("no such column", result.trace[0].sanitized_error.lower())
        self.assertEqual(result.trace[1].status, "SUCCESS")

    def test_pipeline_revalidates_every_retry(self):
        """
        Verifies that if a retry attempts a destructive query,
        the pipeline blocks it via the AST validator before execution.
        """
        mock_adapter = DestructiveRetryMockAdapter()
        pipeline = TextToSqlPipeline(self.db, mock_adapter)
        result = pipeline.run("Test destructive retry")

        # Trace step 1: execution error (missing column)
        self.assertEqual(result.trace[0].status, "EXECUTION_ERROR")
        # Trace step 2: blocked by AST validator (DROP TABLE)
        self.assertEqual(result.trace[1].status, "VALIDATION_FAILED")
        self.assertTrue("Forbidden" in result.trace[1].sanitized_error or "blocked" in result.trace[1].sanitized_error)
        # Trace step 3: success with safe query
        self.assertEqual(result.trace[2].status, "SUCCESS")

    def test_pipeline_max_retry_boundary(self):
        """
        Verifies that pipeline strictly terminates after at most 2 retries (total 3 attempts).
        """
        failing_adapter = AlwaysFailingMockAdapter()
        pipeline = TextToSqlPipeline(self.db, failing_adapter)
        result = pipeline.run("Always fails")

        self.assertFalse(result.success)
        self.assertEqual(result.total_attempts, 3) # 1 initial + 2 retries
        self.assertEqual(len(result.trace), 3)
        self.assertTrue(result.had_retry)
        self.assertIsNotNone(result.final_error)

if __name__ == "__main__":
    unittest.main()
