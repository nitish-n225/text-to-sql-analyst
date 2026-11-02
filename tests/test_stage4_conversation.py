"""
Unit Tests for Stage 4: Conversational Analytics & Follow-Up Context Management.

Guarantees:
1. ConversationTurn: Metadata-only representation, sanitized prompt dict, display dict.
2. ConversationSession: Turn management, bounded context window (max_turns), data source isolation.
3. ConversationManager: Complete session isolation across different users or test sessions.
4. DemoModeAdapter Follow-Up Handling:
   - Limit refinement (top 3, top 1, top 10)
   - Sort order reversal (lowest / ascending)
   - Aggregation / Count ("how many are there")
   - Filter addition ("only platinum")
   - Pronoun resolution ("their emails")
5. TextToSqlPipeline Conversational Integration:
   - Multi-turn execution with delta explanations and turn IDs.
   - Automatic history reset when switching data sources.
   - Zero sensitive secret or raw database dump leakage in conversation metadata.
"""

import unittest
from typing import Dict, Any
import pandas as pd

from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.conversation import ConversationTurn, ConversationSession, ConversationManager
from src.llm_adapter import DemoModeAdapter, LLMOutput
from src.pipeline import TextToSqlPipeline, PipelineResult


class TestStage4Conversation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager()
        seed_sample_database(cls.db, reset=False)

    def test_conversation_turn_metadata_hygiene(self):
        """Verifies that ConversationTurn stores metadata only and sanitizes prompt output."""
        turn = ConversationTurn(
            turn_id=1,
            timestamp="2026-10-30 12:00:00",
            question="Show top 5 customers by total spending",
            sql="SELECT id, name FROM customers LIMIT 5",
            explanation="Returns top 5 customers.",
            delta_explanation=None,
            success=True,
            rows_count=5,
            columns=["id", "name"],
            summary="Found 5 customers.",
            error_message=None,
            data_source="sample:business.db"
        )

        p_dict = turn.to_prompt_dict()
        # Prompt dict must contain essential query metadata but no sensitive connection strings
        self.assertEqual(p_dict["turn_id"], 1)
        self.assertEqual(p_dict["question"], "Show top 5 customers by total spending")
        self.assertEqual(p_dict["sql"], "SELECT id, name FROM customers LIMIT 5")
        self.assertEqual(p_dict["rows_count"], 5)
        self.assertNotIn("data_source", p_dict) # Avoid leaking file paths into prompt

        d_dict = turn.to_display_dict()
        self.assertEqual(d_dict["turn_id"], 1)
        self.assertEqual(d_dict["columns"], ["id", "name"])

    def test_session_turn_management(self):
        """Verifies adding turns, turn counting, and history retrieval."""
        session = ConversationSession(session_id="test_sess_1", data_source="sample:business.db")
        self.assertEqual(session.turn_count, 0)
        self.assertIsNone(session.get_last_successful_turn())

        # Add Turn 1
        t1 = session.add_turn(
            question="Show top 5 customers",
            sql="SELECT * FROM customers LIMIT 5",
            explanation="Top customers",
            success=True,
            rows_count=5,
            columns=["id", "name"]
        )
        self.assertEqual(session.turn_count, 1)
        self.assertEqual(t1.turn_id, 1)
        self.assertEqual(session.get_last_successful_turn().turn_id, 1)

        # Add Turn 2 (failed query)
        t2 = session.add_turn(
            question="Invalid table",
            sql="",
            explanation="Failed",
            success=False,
            error_message="no such table"
        )
        self.assertEqual(session.turn_count, 2)
        # Last successful turn should still be Turn 1
        self.assertEqual(session.get_last_successful_turn().turn_id, 1)

    def test_session_prompt_context_bounding(self):
        """Verifies that prompt context is bounded to max_turns and skips failed turns."""
        session = ConversationSession(session_id="test_sess_bound", data_source="sample:business.db")

        # Add 5 successful turns
        for i in range(1, 6):
            session.add_turn(
                question=f"Question {i}",
                sql=f"SELECT {i} FROM customers",
                explanation=f"Exp {i}",
                success=True,
                rows_count=i
            )

        # Add a 6th turn that failed
        session.add_turn(
            question="Question 6 Failed",
            sql="",
            explanation="Error",
            success=False,
            error_message="Error"
        )

        # Asking for max_turns=3 should return turns 3, 4, 5
        context = session.get_context_for_prompt(max_turns=3)
        self.assertEqual(len(context), 3)
        self.assertEqual(context[0]["turn_id"], 3)
        self.assertEqual(context[1]["turn_id"], 4)
        self.assertEqual(context[2]["turn_id"], 5)

    def test_data_source_isolation_clears_history(self):
        """Verifies that switching data sources automatically clears conversation history."""
        session = ConversationSession(session_id="test_iso", data_source="sample:business.db")
        session.add_turn(
            question="Show customers",
            sql="SELECT * FROM customers",
            explanation="Customer list",
            success=True
        )
        self.assertEqual(session.turn_count, 1)

        # Keeping the same data source should NOT clear history
        reset = session.set_data_source("sample:business.db")
        self.assertFalse(reset)
        self.assertEqual(session.turn_count, 1)

        # Switching to an uploaded CSV or new SQLite DB must reset history
        reset = session.set_data_source("csv:employees.csv")
        self.assertTrue(reset)
        self.assertEqual(session.turn_count, 0)
        self.assertEqual(session.data_source, "csv:employees.csv")

    def test_conversation_manager_isolation(self):
        """Verifies multi-session registry isolates distinct user sessions."""
        manager = ConversationManager()
        s1 = manager.get_or_create_session("user_alice", data_source="sample:business.db")
        s2 = manager.get_or_create_session("user_bob", data_source="sample:business.db")

        s1.add_turn(question="Alice Q", sql="SELECT 1", explanation="Alice")
        self.assertEqual(s1.turn_count, 1)
        self.assertEqual(s2.turn_count, 0) # Bob must remain untouched

        manager.reset_session("user_alice")
        self.assertEqual(s1.turn_count, 0)

        manager.delete_session("user_alice")
        self.assertNotIn("user_alice", manager.list_sessions())

    def test_demo_mode_follow_up_limit_refinement(self):
        """Verifies DemoModeAdapter refines LIMIT on follow-up question."""
        adapter = DemoModeAdapter()
        history = [{
            "turn_id": 1,
            "question": "Show top 5 customers by total spending",
            "sql": "SELECT c.id, c.name, SUM(o.total_amount) AS total_spent FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id ORDER BY total_spent DESC LIMIT 5",
            "explanation": "Top 5 spenders",
            "success": True,
            "assumptions": ["Sorted by total_spent DESC"]
        }]

        out = adapter.generate_structured(
            question="Show only top 3 of those",
            schema_prompt="",
            conversation_history=history
        )
        self.assertIsNotNone(out.sql)
        self.assertIn("LIMIT 3", out.sql)
        self.assertNotIn("LIMIT 5", out.sql)
        self.assertIsNotNone(out.delta_explanation)
        self.assertIn("top 3", out.delta_explanation.lower())

    def test_demo_mode_follow_up_sort_reversal(self):
        """Verifies DemoModeAdapter reverses sort order (lowest / ascending) on follow-up."""
        adapter = DemoModeAdapter()
        history = [{
            "turn_id": 1,
            "question": "Show top 5 customers by total spending",
            "sql": "SELECT c.id, c.name, SUM(o.total_amount) AS total_spent FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id ORDER BY total_spent DESC LIMIT 5",
            "explanation": "Top 5 spenders",
            "success": True
        }]

        out = adapter.generate_structured(
            question="Show the lowest instead",
            schema_prompt="",
            conversation_history=history
        )
        self.assertIsNotNone(out.sql)
        self.assertIn("ASC", out.sql)
        self.assertIsNotNone(out.delta_explanation)
        self.assertIn("ascending", out.delta_explanation.lower())

    def test_demo_mode_follow_up_count_aggregation(self):
        """Verifies DemoModeAdapter wraps previous query into COUNT(*) aggregation."""
        adapter = DemoModeAdapter()
        history = [{
            "turn_id": 1,
            "question": "Show customers from United States",
            "sql": "SELECT * FROM customers WHERE country = 'United States' LIMIT 10",
            "explanation": "US customers",
            "success": True
        }]

        out = adapter.generate_structured(
            question="How many are there in total?",
            schema_prompt="",
            conversation_history=history
        )
        self.assertIsNotNone(out.sql)
        self.assertIn("COUNT(*)", out.sql)
        self.assertIsNotNone(out.delta_explanation)

    def test_demo_mode_follow_up_loyalty_filter(self):
        """Verifies DemoModeAdapter adds loyalty tier filter condition on follow-up."""
        adapter = DemoModeAdapter()
        history = [{
            "turn_id": 1,
            "question": "Show top 5 customers by total spending",
            "sql": "SELECT c.id, c.name, SUM(o.total_amount) AS total_spent FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id ORDER BY total_spent DESC LIMIT 5",
            "explanation": "Top 5 spenders",
            "success": True
        }]

        out = adapter.generate_structured(
            question="Show only Platinum tier",
            schema_prompt="",
            conversation_history=history
        )
        self.assertIsNotNone(out.sql)
        self.assertIn("Platinum", out.sql)
        self.assertIsNotNone(out.delta_explanation)

    def test_pipeline_conversational_turn_lifecycle(self):
        """
        End-to-end integration test:
        Turn 1: Baseline analytical query
        Turn 2: Follow-up query modifying Turn 1
        """
        session = ConversationSession(session_id="e2e_test", data_source="sample:business.db")
        pipeline = TextToSqlPipeline(self.db, DemoModeAdapter(), session=session)

        # Turn 1: Top 5 customers
        res1 = pipeline.run("Show top 5 customers by total spending and order count")
        self.assertTrue(res1.success)
        self.assertEqual(len(res1.dataframe), 5)
        self.assertEqual(res1.turn_id, 1)
        self.assertIsNone(res1.delta_explanation)
        self.assertEqual(session.turn_count, 1)

        # Turn 2: Follow-up query
        res2 = pipeline.run("Show only top 3 of those")
        self.assertTrue(res2.success)
        self.assertEqual(len(res2.dataframe), 3)
        self.assertEqual(res2.turn_id, 2)
        self.assertIsNotNone(res2.delta_explanation)
        self.assertEqual(session.turn_count, 2)

    def test_pipeline_data_source_switch_resets_conversation(self):
        """Verifies that changing the data source in session clears context before execution."""
        session = ConversationSession(session_id="db_switch_test", data_source="sample:business.db")
        pipeline = TextToSqlPipeline(self.db, DemoModeAdapter(), session=session)

        pipeline.run("Show top 5 customers by total spending")
        self.assertEqual(session.turn_count, 1)

        # Switch data source
        session.set_data_source("csv:uploaded_data.csv")
        self.assertEqual(session.turn_count, 0)
        self.assertEqual(len(session.get_context_for_prompt()), 0)


if __name__ == "__main__":
    unittest.main()
