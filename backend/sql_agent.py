import os
import re
import json
import time
import requests
import sys
from typing import Dict, Any, List, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from backend.db_manager import db_manager
except ImportError:
    from db_manager import db_manager


class TextToSqlAgent:
    def __init__(self):
        self.default_model = "offline-smart"
        self.max_retries = 3

    def _call_gemini(self, prompt: str, api_key: str, model: str = "gemini-1.5-flash") -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}
        }
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        res.raise_for_status()
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_openai_compatible(self, prompt: str, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini") -> str:
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert SQL analyst. Generate only clean SQLite SQL queries without explanation or markdown when asked, unless requested otherwise."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"]

    def _call_ollama(self, prompt: str, base_url: str = "http://localhost:11434", model: str = "llama3") -> str:
        url = f"{base_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }
        res = requests.post(url, json=payload, timeout=45)
        res.raise_for_status()
        return res.json().get("response", "")

    def _clean_sql(self, raw_text: str) -> str:
        """Strips markdown code fences, comments, and whitespace."""
        clean = re.sub(r"```(?:sql)?\n?", "", raw_text)
        clean = clean.replace("```", "").strip()
        # Find first SELECT or WITH statement if model output conversational text
        m = re.search(r"\b(SELECT|WITH)\b.*", clean, re.IGNORECASE | re.DOTALL)
        if m:
            clean = m.group(0)
        # Remove trailing semicolon if present
        clean = clean.rstrip(";").strip()
        return clean

    def _offline_generate_sql(self, question: str, schema_str: str, db_name: str, is_retry: bool = False, error_msg: Optional[str] = None, induce_error: bool = False) -> str:
        """
        Intelligent offline heuristic SQL generator that produces accurate queries
        for standard schemas and supports error injection for demonstration.
        """
        q = question.lower()
        db = db_name.lower()

        # If induce_error is requested on attempt 1 (not retry), inject a deliberate schema error
        if induce_error and not is_retry:
            if "ecommerce" in db:
                return "SELECT customer_name, SUM(total_price) AS revenue FROM orders JOIN customers ON orders.customer_id = customers.id GROUP BY customer_name ORDER BY revenue DESC LIMIT 5"
            elif "hr" in db or "company" in db:
                return "SELECT department, AVG(base_salary) AS avg_sal FROM employees GROUP BY department"
            elif "health" in db:
                return "SELECT patient_full_name, diagnosis_name FROM appointments JOIN patients ON appointments.patient_id = patients.id LIMIT 5"
            else:
                return "SELECT non_existent_column, COUNT(*) FROM sqlite_master"

        # E-Commerce Database Queries
        if "ecommerce" in db:
            if any(w in q for w in ["top", "highest", "best"]) and any(w in q for w in ["customer", "buyer", "spenders"]):
                return "SELECT c.id, c.name, c.loyalty_tier, c.country, ROUND(SUM(o.total_amount), 2) AS total_spent, COUNT(o.id) AS total_orders FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name, c.loyalty_tier, c.country ORDER BY total_spent DESC LIMIT 5"
            elif "category" in q or "categories" in q:
                return "SELECT c.name AS category_name, COUNT(p.id) AS product_count, ROUND(AVG(p.price), 2) AS avg_price, ROUND(AVG(p.rating), 2) AS avg_rating FROM categories c JOIN products p ON c.id = p.category_id GROUP BY c.id, c.name ORDER BY product_count DESC"
            elif "rating" in q or "rated" in q or "review" in q:
                return "SELECT p.name AS product_name, c.name AS category, p.price, p.rating, p.stock_quantity FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.rating DESC, p.price DESC LIMIT 10"
            elif "revenue" in q or "sales" in q or "status" in q:
                return "SELECT status, COUNT(*) AS order_count, ROUND(SUM(total_amount), 2) AS total_revenue, ROUND(AVG(total_amount), 2) AS avg_order_value FROM orders GROUP BY status ORDER BY total_revenue DESC"
            elif "payment" in q:
                return "SELECT payment_method, COUNT(*) AS transaction_count, ROUND(SUM(total_amount), 2) AS total_amount FROM orders GROUP BY payment_method ORDER BY transaction_count DESC"
            elif "city" in q or "shipping" in q:
                return "SELECT shipping_city, COUNT(id) AS total_orders, ROUND(SUM(total_amount), 2) AS city_revenue FROM orders GROUP BY shipping_city ORDER BY city_revenue DESC LIMIT 8"
            elif "loyalty" in q or "tier" in q:
                return "SELECT loyalty_tier, COUNT(*) AS customer_count FROM customers GROUP BY loyalty_tier ORDER BY customer_count DESC"
            else:
                return "SELECT p.name AS product_name, c.name AS category, p.price, p.stock_quantity, p.rating FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.rating DESC LIMIT 10"

        # Company HR Database Queries
        elif "hr" in db or "company" in db:
            if "salary" in q and ("average" in q or "highest" in q or "dept" in q or "department" in q):
                return "SELECT d.name AS department_name, COUNT(e.id) AS employee_count, ROUND(AVG(e.salary), 2) AS avg_salary, MAX(e.salary) AS max_salary, d.budget FROM departments d JOIN employees e ON d.id = e.department_id GROUP BY d.id, d.name ORDER BY avg_salary DESC"
            elif "remote" in q or "hybrid" in q:
                return "SELECT remote_status, COUNT(*) AS employee_count, ROUND(AVG(salary), 2) AS avg_salary, ROUND(AVG(performance_rating), 2) AS avg_performance FROM employees GROUP BY remote_status"
            elif "performance" in q or "top employee" in q or "rating" in q:
                return "SELECT e.name, d.name AS department, e.job_title, e.salary, e.performance_rating, e.remote_status FROM employees e JOIN departments d ON e.department_id = d.id WHERE e.performance_rating >= 4.7 ORDER BY e.performance_rating DESC, e.salary DESC"
            elif "project" in q or "budget" in q:
                return "SELECT p.title, d.name AS department, p.budget, p.status, p.start_date, p.end_date FROM projects p JOIN departments d ON p.department_id = d.id ORDER BY p.budget DESC"
            else:
                return "SELECT e.name, d.name AS department, e.job_title, e.salary, e.hire_date FROM employees e JOIN departments d ON e.department_id = d.id ORDER BY e.salary DESC LIMIT 10"

        # Healthcare Database Queries
        elif "health" in db:
            if "doctor" in q or "specialty" in q:
                return "SELECT name, specialty, years_experience, consultation_fee FROM doctors ORDER BY years_experience DESC"
            elif "diagnosis" in q or "disease" in q or "condition" in q:
                return "SELECT diagnosis, COUNT(*) AS case_count, ROUND(AVG(billing_amount), 2) AS avg_cost, ROUND(SUM(billing_amount), 2) AS total_billing FROM appointments WHERE diagnosis IS NOT NULL GROUP BY diagnosis ORDER BY case_count DESC"
            elif "insurance" in q or "provider" in q:
                return "SELECT insurance_provider, COUNT(*) AS patient_count FROM patients GROUP BY insurance_provider ORDER BY patient_count DESC"
            elif "blood" in q:
                return "SELECT blood_type, COUNT(*) AS total_patients FROM patients GROUP BY blood_type ORDER BY total_patients DESC"
            else:
                return "SELECT a.id AS appointment_id, p.name AS patient_name, d.name AS doctor_name, a.appointment_date, a.status, a.diagnosis, a.billing_amount FROM appointments a JOIN patients p ON a.patient_id = p.id JOIN doctors d ON a.doctor_id = d.id ORDER BY a.appointment_date DESC LIMIT 10"

        # Generic fallback
        return "SELECT name FROM sqlite_master WHERE type='table'"

    def _synthesize_answer(self, question: str, sql: str, rows: List[Dict[str, Any]], error: Optional[str] = None) -> str:
        """Generates a crisp plain English summary of the SQL analysis results."""
        if error:
            return f"The analysis could not be completed because an error occurred during SQL execution: {error}"

        if not rows:
            return "The query executed successfully, but returned 0 rows. No matching records were found matching your criteria in the database."

        count = len(rows)
        first_row = rows[0]
        keys = list(first_row.keys())

        # Construct intelligent summary
        summary_parts = [f"Found **{count} record{'s' if count > 1 else ''}** answering your question."]

        # Check for top item highlight
        if len(keys) >= 2:
            label_key = keys[0] if isinstance(first_row[keys[0]], str) else keys[1]
            metric_key = None
            for k in keys:
                if isinstance(first_row[k], (int, float)) and not k.endswith("_id") and k != "id":
                    metric_key = k
                    break

            if metric_key and label_key in first_row:
                top_val = first_row[metric_key]
                if isinstance(top_val, float):
                    top_val_str = f"{top_val:,.2f}"
                else:
                    top_val_str = f"{top_val:,}"
                summary_parts.append(f"Top result: **{first_row[label_key]}** with {metric_key.replace('_', ' ')} of **{top_val_str}**.")

        return " ".join(summary_parts)

    def _determine_chart_config(self, columns: List[str], rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Determines best chart type and datasets for the result table."""
        if not rows or len(rows) < 2 or not columns:
            return None

        # Categorize columns
        label_col = None
        numeric_cols = []

        for col in columns:
            val = rows[0].get(col)
            if isinstance(val, (int, float)) and not col.lower().endswith("id") and col.lower() != "id":
                numeric_cols.append(col)
            elif isinstance(val, str) and label_col is None:
                label_col = col

        if not label_col and columns:
            label_col = columns[0]

        if not numeric_cols:
            return None

        chart_type = "bar"
        # Check if label looks like dates
        first_label = str(rows[0].get(label_col, ""))
        if re.search(r"\d{4}-\d{2}", first_label):
            chart_type = "line"
        elif len(rows) <= 6 and len(numeric_cols) == 1:
            chart_type = "doughnut"

        labels = [str(r.get(label_col, "")) for r in rows[:15]]
        datasets = []
        palette = [
            "rgba(99, 102, 241, 0.85)",   # Indigo
            "rgba(14, 165, 233, 0.85)",   # Sky
            "rgba(168, 85, 247, 0.85)",   # Purple
            "rgba(16, 185, 129, 0.85)",   # Emerald
            "rgba(244, 63, 94, 0.85)"     # Rose
        ]

        for idx, num_col in enumerate(numeric_cols[:3]):
            data_points = [r.get(num_col, 0) for r in rows[:15]]
            color = palette[idx % len(palette)]
            datasets.append({
                "label": num_col.replace("_", " ").title(),
                "data": data_points,
                "backgroundColor": color if chart_type != "line" else "rgba(99, 102, 241, 0.15)",
                "borderColor": color.replace("0.85", "1.0"),
                "borderWidth": 2,
                "fill": (chart_type == "line")
            })

        return {
            "type": chart_type,
            "labels": labels,
            "datasets": datasets
        }

    def run_analyst_pipeline(
        self,
        question: str,
        db_name: Optional[str] = None,
        provider: str = "offline",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        simulate_error: bool = False,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Main pipeline executing:
        1. Plain English -> LLM writes SQL
        2. Execution against SQLite
        3. If error -> feeds error + query back to LLM for retry
        4. When successful -> returns Answer + Query Used + Schema Context + Retry Trace + Data Table
        """
        db = db_name or db_manager.active_db
        schema_prompt = db_manager.get_schema_prompt_string(db)
        
        retry_trace = []
        attempt = 1
        current_sql = ""
        last_error = None
        execution_result = {}
        start_overall = time.time()

        while attempt <= max_retries:
            attempt_start = time.time()
            is_retry = (attempt > 1)
            
            # 1. Generate SQL
            if provider == "gemini" and api_key:
                if is_retry:
                    prompt = (
                        f"You are an expert SQLite analyst. A previously generated SQL query failed with an error.\n\n"
                        f"Database Schema:\n{schema_prompt}\n\n"
                        f"User Question:\n{question}\n\n"
                        f"Failed SQL Query:\n{current_sql}\n\n"
                        f"Execution Error Message:\n{last_error}\n\n"
                        f"Analyze the error, fix the table/column names, syntax, or join conditions, and return ONLY the corrected valid SQLite query."
                    )
                else:
                    prompt = (
                        f"You are an expert SQLite analyst.\n\n"
                        f"Database Schema:\n{schema_prompt}\n\n"
                        f"User Question:\n{question}\n\n"
                        f"Write a valid SQLite query to answer the question. Return ONLY the raw SQL code without explanation or markdown."
                    )
                raw_response = self._call_gemini(prompt, api_key, model or "gemini-1.5-flash")
                current_sql = self._clean_sql(raw_response)

            elif provider in ["openai", "groq", "custom"] and api_key:
                target_base = base_url or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")
                target_model = model or ("llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o-mini")
                
                if is_retry:
                    prompt = (
                        f"Previous query failed on SQLite.\n"
                        f"Error: {last_error}\n"
                        f"Failed Query: {current_sql}\n"
                        f"Schema:\n{schema_prompt}\n"
                        f"Question: {question}\n\n"
                        f"Rewrite and fix the SQL query. Return ONLY the corrected SQLite statement."
                    )
                else:
                    prompt = (
                        f"Given SQLite schema:\n{schema_prompt}\n\n"
                        f"Answer question: {question}\n"
                        f"Return ONLY valid SQLite SQL."
                    )
                raw_response = self._call_openai_compatible(prompt, api_key, target_base, target_model)
                current_sql = self._clean_sql(raw_response)

            elif provider == "ollama":
                target_base = base_url or "http://localhost:11434"
                target_model = model or "llama3"
                prompt = (
                    f"SQLite Schema:\n{schema_prompt}\n"
                    f"Question: {question}\n"
                    + (f"Previous query failed: {current_sql}\nError: {last_error}\nFix the query:" if is_retry else "Return only the SQL query:")
                )
                raw_response = self._call_ollama(prompt, target_base, target_model)
                current_sql = self._clean_sql(raw_response)

            else:
                # Built-in Smart Offline Engine
                # If simulate_error is True and this is attempt 1, intentionally inject an error
                current_sql = self._offline_generate_sql(
                    question=question,
                    schema_str=schema_prompt,
                    db_name=db,
                    is_retry=is_retry,
                    error_msg=last_error,
                    induce_error=simulate_error
                )

            # 2. Execute SQL
            exec_res = db_manager.execute_query(current_sql, db_name=db)
            attempt_duration = round((time.time() - attempt_start) * 1000, 2)

            if exec_res["success"]:
                retry_trace.append({
                    "attempt": attempt,
                    "query": current_sql,
                    "status": "success",
                    "error": None,
                    "duration_ms": attempt_duration,
                    "rows_count": exec_res["total_rows"]
                })
                execution_result = exec_res
                break
            else:
                last_error = exec_res["error"]
                retry_trace.append({
                    "attempt": attempt,
                    "query": current_sql,
                    "status": "failed",
                    "error": last_error,
                    "duration_ms": attempt_duration,
                    "rows_count": 0
                })
                # If simulate_error was active on attempt 1, disable it for retry so it fixes itself
                if simulate_error:
                    simulate_error = False

                attempt += 1

        overall_time = round((time.time() - start_overall) * 1000, 2)
        success = execution_result.get("success", False)

        # 3. Plain English Answer Synthesis
        plain_answer = self._synthesize_answer(
            question=question,
            sql=current_sql,
            rows=execution_result.get("rows", []),
            error=last_error if not success else None
        )

        # 4. Chart Suggestions
        chart_data = None
        if success:
            chart_data = self._determine_chart_config(
                execution_result.get("columns", []),
                execution_result.get("rows", [])
            )

        return {
            "success": success,
            "question": question,
            "database": db,
            "query_used": current_sql,
            "answer": plain_answer,
            "total_attempts": len(retry_trace),
            "had_retry": len(retry_trace) > 1,
            "retry_trace": retry_trace,
            "columns": execution_result.get("columns", []),
            "rows": execution_result.get("rows", []),
            "total_rows": execution_result.get("total_rows", 0),
            "execution_time_ms": execution_result.get("execution_time_ms", 0),
            "total_duration_ms": overall_time,
            "chart_data": chart_data,
            "final_error": last_error if not success else None
        }

sql_agent = TextToSqlAgent()
