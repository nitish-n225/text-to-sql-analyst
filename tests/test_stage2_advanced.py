"""
Automated Test Suite for Stage 2 Advanced Text-to-SQL Intelligence:
- Multi-table JOINs and foreign-key relationships (4 tables: customers -> orders -> order_items -> products)
- Aggregation, date filtering, HAVING clauses, and top-N sorting
- Invalid/hallucinated tables and columns detection via SchemaContextBuilder
- Socratic ambiguity detection and clarification handling
- Corrected SQL being strictly revalidated on every retry
- Maximum retry boundary (at most 2 retries, total 3 attempts)
- Destructive SQL remaining blocked during correction retries
- Demo mode operating deterministically without external API calls
- Diagnostic observability logging and secrets redaction
"""

import unittest
import pandas as pd
from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.validator import validate_sql
from src.schema_context import SchemaContextBuilder
from src.llm_adapter import BaseLLMAdapter, DemoModeAdapter, LLMOutput
from src.pipeline import TextToSqlPipeline, sanitize_error_context, MAX_CORRECTION_RETRIES
from src.logger import redact_sensitive_info, observability

class TestStage2Advanced(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager()
        seed_sample_database(cls.db, reset=False)
        cls.schema_builder = SchemaContextBuilder(cls.db)

    def test_multitable_joins_and_fk_relationships(self):
        """
        Tests multi-table JOIN across 4 tables:
        customers -> orders -> order_items -> products.
        """
        adapter = DemoModeAdapter()
        pipeline = TextToSqlPipeline(self.db, adapter)

        result = pipeline.run("Show customer product purchase history")
        self.assertTrue(result.success)
        self.assertIsNotNone(result.dataframe)
        self.assertGreater(len(result.dataframe), 0)

        df = result.dataframe
        cols = list(df.columns)
        self.assertIn("customer_name", cols)
        self.assertIn("product_name", cols)
        self.assertIn("order_date", cols)

        # Check that SQL joins all four tables
        sql_lower = result.query_used.lower()
        self.assertIn("customers", sql_lower)
        self.assertIn("orders", sql_lower)
        self.assertIn("order_items", sql_lower)
        self.assertIn("products", sql_lower)

    def test_aggregation_date_filtering_and_top_n(self):
        """
        Tests analytical queries with date filtering (strftime),
        aggregations (SUM, COUNT), and HAVING clauses.
        """
        adapter = DemoModeAdapter()
        pipeline = TextToSqlPipeline(self.db, adapter)

        # Monthly aggregation test
        res_monthly = pipeline.run("Show monthly sales trends")
        self.assertTrue(res_monthly.success)
        self.assertIn("order_month", res_monthly.dataframe.columns)
        self.assertIn("monthly_revenue", res_monthly.dataframe.columns)

        # HAVING clause test
        res_having = pipeline.run("Show repeat frequent buyers with more than 3 orders")
        self.assertTrue(res_having.success)
        self.assertIn("having", res_having.query_used.lower())
        self.assertGreater(len(res_having.dataframe), 0)

    def test_invalid_tables_and_columns_semantic_validation(self):
        """
        Verifies that SchemaContextBuilder detects hallucinated tables and columns.
        """
        # Hallucinated table
        bad_table_sql = "SELECT id, name FROM non_existent_clients WHERE id = 1"
        ok, err = self.schema_builder.validate_schema_references(bad_table_sql)
        self.assertFalse(ok)
        self.assertIn("non_existent_clients", err.lower())

        # Hallucinated column
        bad_col_sql = "SELECT id, imaginary_discount_field FROM products"
        ok_col, err_col = self.schema_builder.validate_schema_references(bad_col_sql)
        self.assertFalse(ok_col)
        self.assertIn("imaginary_discount_field", err_col.lower())

        # Valid query
        valid_sql = "SELECT p.id, p.name, p.price, c.name FROM products p JOIN customers c"
        ok_valid, err_valid = self.schema_builder.validate_schema_references(valid_sql)
        self.assertTrue(ok_valid)
        self.assertIsNone(err_valid)

    def test_ambiguous_questions_handling(self):
        """
        Verifies that ambiguous questions trigger clarification requests.
        """
        adapter = DemoModeAdapter()
        pipeline = TextToSqlPipeline(self.db, adapter)

        ambiguous_questions = [
            "Show best",
            "What is the best",
            "Show sales",
            "orders",
            "Compare customer tiers"
        ]

        for q in ambiguous_questions:
            res = pipeline.run(q)
            self.assertFalse(res.success)
            self.assertTrue(res.needs_clarification, f"Expected needs_clarification for '{q}'")
            self.assertIsNotNone(res.clarification_question)
            self.assertGreater(len(res.clarification_options), 0)
            self.assertEqual(res.error_category, "AMBIGUITY_DETECTED")

    def test_corrected_sql_revalidated_on_retry(self):
        """
        Uses a deterministic fake model adapter to verify that retried queries
        are strictly revalidated before database execution.
        """
        class RevalidationFakeAdapter(BaseLLMAdapter):
            def __init__(self):
                self.calls = 0

            def generate_structured(self, question, schema_prompt, error_feedback=None):
                self.calls += 1
                if self.calls == 1:
                    # Attempt 1: Syntax error
                    return LLMOutput(sql="SELECT broken FROM customers", explanation="Attempt 1")
                elif self.calls == 2:
                    # Attempt 2 (Retry 1): Malicious query
                    return LLMOutput(sql="DROP TABLE orders;", explanation="Attempt 2")
                else:
                    # Attempt 3 (Retry 2): Valid query
                    return LLMOutput(sql="SELECT id, name FROM customers LIMIT 5", explanation="Attempt 3")

            def synthesize_summary(self, question, query, df):
                return "Success summary"

        fake_adapter = RevalidationFakeAdapter()
        pipeline = TextToSqlPipeline(self.db, fake_adapter)
        result = pipeline.run("Test retry revalidation")

        self.assertEqual(len(result.trace), 3)
        # Attempt 1 failed at DB execution (no column 'broken')
        self.assertEqual(result.trace[0].status, "EXECUTION_ERROR")
        # Attempt 2 failed at AST validation (DROP TABLE rejected before reaching DB)
        self.assertEqual(result.trace[1].status, "VALIDATION_FAILED")
        self.assertEqual(result.trace[1].error_category, "VALIDATION_ERROR")
        # Attempt 3 succeeded
        self.assertEqual(result.trace[2].status, "SUCCESS")
        self.assertTrue(result.success)

    def test_maximum_retry_boundary(self):
        """
        Verifies that pipeline never retries more than 2 times (at most 3 attempts total).
        """
        class PerpetualFailureAdapter(BaseLLMAdapter):
            def generate_structured(self, question, schema_prompt, error_feedback=None):
                return LLMOutput(sql="SELECT fake_col FROM customers", explanation="Always failing")

            def synthesize_summary(self, question, query, df):
                return "Failed"

        fake_adapter = PerpetualFailureAdapter()
        pipeline = TextToSqlPipeline(self.db, fake_adapter)
        result = pipeline.run("Test max retries")

        self.assertFalse(result.success)
        self.assertEqual(result.total_attempts, 3)
        self.assertEqual(len(result.trace), 3)
        self.assertTrue(result.had_retry)
        self.assertEqual(result.error_category, "DATABASE_ERROR")

    def test_destructive_sql_blocked_during_correction(self):
        """
        Verifies that destructive SQL (INSERT, UPDATE, DELETE, ALTER, DROP)
        is completely blocked during retry attempts.
        """
        destructive_statements = [
            "DELETE FROM orders WHERE id = 1;",
            "UPDATE customers SET loyalty_tier = 'Platinum';",
            "INSERT INTO products (name, category, price) VALUES ('X', 'Y', 10);",
            "ALTER TABLE customers ADD COLUMN hack TEXT;"
        ]

        for stmt in destructive_statements:
            class DestructiveInjectionAdapter(BaseLLMAdapter):
                def __init__(self, query_to_inject):
                    self.query_to_inject = query_to_inject
                    self.call_count = 0

                def generate_structured(self, question, schema_prompt, error_feedback=None):
                    self.call_count += 1
                    if self.call_count == 1:
                        return LLMOutput(sql="SELECT invalid_col FROM products", explanation="Initial error")
                    return LLMOutput(sql=self.query_to_inject, explanation="Injected destructive query")

                def synthesize_summary(self, question, query, df):
                    return ""

            fake_adapter = DestructiveInjectionAdapter(stmt)
            pipeline = TextToSqlPipeline(self.db, fake_adapter)
            res = pipeline.run("Test destructive block")

            # Check that attempt 2 was rejected by the safety validator
            self.assertEqual(res.trace[1].status, "VALIDATION_FAILED")
            self.assertEqual(res.trace[1].error_category, "VALIDATION_ERROR")
            self.assertTrue("blocked" in res.trace[1].sanitized_error.lower() or "forbidden" in res.trace[1].sanitized_error.lower())

    def test_demo_mode_operates_without_external_api_calls(self):
        """
        Verifies that DemoMode operates 100% offline without network or API calls.
        """
        adapter = DemoModeAdapter()
        self.assertTrue(adapter.is_demo)
        self.assertIn("No External LLM", adapter.label)

        # Run multiple distinct questions
        for q in [
            "Show top 5 customers by total spending",
            "What are the product counts and average prices by category?",
            "Show order counts and total revenue grouped by order status",
            "Find the highest rated products with current inventory",
            "Show customer counts grouped by loyalty tier",
            "Which destination cities generated the highest total sales volume?"
        ]:
            out = adapter.generate_structured(q, schema_prompt="")
            self.assertIsNotNone(out.sql)
            self.assertGreater(len(out.explanation), 5)
            self.assertIsInstance(out.assumptions, list)

    def test_structured_output_fields(self):
        """
        Verifies pipeline results include structured explanation and assumptions.
        """
        pipeline = TextToSqlPipeline(self.db, DemoModeAdapter())
        res = pipeline.run("Show top 5 customers by total spending")

        self.assertTrue(res.success)
        self.assertGreater(len(res.explanation), 5)
        self.assertIsInstance(res.assumptions, list)
        self.assertGreater(len(res.assumptions), 0)

    def test_diagnostic_logging_and_redaction(self):
        """
        Verifies that the diagnostic logger redacts sensitive API keys and paths.
        """
        sensitive_string = (
            "Calling API with Authorization: Bearer sk-proj-1234567890abcdef1234567890 "
            "and key=AIzaSy1234567890abcdef1234567890 "
            r"loading from C:\Users\Administrator\Secrets\app.db"
        )
        redacted = redact_sensitive_info(sensitive_string)

        self.assertNotIn("sk-proj-1234567890abcdef", redacted)
        self.assertNotIn("AIzaSy1234567890abcdef", redacted)
        self.assertNotIn(r"C:\Users\Administrator\Secrets", redacted)
        self.assertIn("[REDACTED_TOKEN]", redacted)
        self.assertTrue("[REDACTED_KEY]" in redacted or "[REDACTED_GEMINI_KEY]" in redacted)
        self.assertIn("<local_path>", redacted)


if __name__ == "__main__":
    unittest.main()
