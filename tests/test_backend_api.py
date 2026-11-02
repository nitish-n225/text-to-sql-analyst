import os
import unittest
import tempfile
from fastapi.testclient import TestClient

from backend.main import app
from backend.db_manager import db_manager


class TestBackendApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_get_databases(self):
        response = self.client.get("/api/databases")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("databases", data)
        self.assertIn("active_db", data)
        db_names = [d["filename"] for d in data["databases"]]
        self.assertIn("ecommerce.db", db_names)
        self.assertIn("company_hr.db", db_names)
        self.assertIn("healthcare.db", db_names)

    def test_02_select_database(self):
        # Valid database
        resp = self.client.post("/api/databases/select", json={"db_name": "company_hr.db"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["active_db"], "company_hr.db")

        # Invalid database
        resp_err = self.client.post("/api/databases/select", json={"db_name": "non_existent.db"})
        self.assertEqual(resp_err.status_code, 404)

        # Reset back to ecommerce.db
        self.client.post("/api/databases/select", json={"db_name": "ecommerce.db"})

    def test_03_get_schema(self):
        resp = self.client.get("/api/schema?db_name=ecommerce.db")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["database"], "ecommerce.db")
        table_names = [t["table_name"] for t in data["tables"]]
        self.assertIn("customers", table_names)
        self.assertIn("orders", table_names)
        self.assertIn("products", table_names)

    def test_04_get_prompts(self):
        resp = self.client.get("/api/prompts")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("ecommerce.db", data)
        self.assertIn("company_hr.db", data)
        self.assertIn("healthcare.db", data)
        self.assertTrue(len(data["ecommerce.db"]) >= 4)

    def test_05_natural_query_ecommerce(self):
        resp = self.client.post("/api/query/natural", json={
            "question": "Show top 5 customers by total spending",
            "db_name": "ecommerce.db",
            "provider": "offline"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("SELECT", data["query_used"].upper())
        self.assertGreater(len(data["rows"]), 0)
        self.assertIn("answer", data)

    def test_06_natural_query_company_hr(self):
        resp = self.client.post("/api/query/natural", json={
            "question": "Which department has the highest average salary?",
            "db_name": "company_hr.db",
            "provider": "offline"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("SELECT", data["query_used"].upper())
        self.assertGreater(len(data["rows"]), 0)

    def test_07_natural_query_healthcare(self):
        resp = self.client.post("/api/query/natural", json={
            "question": "List all doctors ordered by years of experience and consultation fee",
            "db_name": "healthcare.db",
            "provider": "offline"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("SELECT", data["query_used"].upper())
        self.assertGreater(len(data["rows"]), 0)

    def test_08_natural_query_self_healing_retry(self):
        resp = self.client.post("/api/query/natural", json={
            "question": "Show top 5 customers by total spending",
            "db_name": "ecommerce.db",
            "provider": "offline",
            "simulate_error": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["had_retry"])
        self.assertEqual(data["total_attempts"], 2)
        # Attempt 1 should be failed, attempt 2 should be success
        trace = data["retry_trace"]
        self.assertEqual(trace[0]["status"], "failed")
        self.assertEqual(trace[1]["status"], "success")

    def test_09_raw_sql_execution(self):
        resp = self.client.post("/api/query/sql", json={
            "query": "SELECT COUNT(*) as cnt FROM customers",
            "db_name": "ecommerce.db"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["rows"][0]["cnt"], 50)

    def test_10_raw_sql_blocks_mutation(self):
        resp = self.client.post("/api/query/sql", json={
            "query": "DELETE FROM customers WHERE id = 1",
            "db_name": "ecommerce.db",
            "allow_mutation": False
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertIn("Security Notice", data["error"])

    def test_11_explain_query(self):
        resp = self.client.post("/api/query/explain", json={
            "query": "SELECT * FROM orders WHERE total_amount > 100",
            "db_name": "ecommerce.db"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreater(len(data["rows"]), 0)

    def test_12_frontend_index_served(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<title>", resp.text)
        self.assertIn("Text-to-SQL Analyst", resp.text)


if __name__ == "__main__":
    unittest.main()
