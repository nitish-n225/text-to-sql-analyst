import os
import sys
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_manager import db_manager, DATA_DIR
from sql_agent import sql_agent
import seed_data

app = FastAPI(title="Text-to-SQL Analyst API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

class NaturalQueryRequest(BaseModel):
    question: str
    db_name: Optional[str] = None
    provider: Optional[str] = "offline"
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    simulate_error: Optional[bool] = False
    max_retries: Optional[int] = 3

class RawSqlRequest(BaseModel):
    query: str
    db_name: Optional[str] = None
    allow_mutation: Optional[bool] = False

class SelectDbRequest(BaseModel):
    db_name: str

@app.get("/api/databases")
def get_databases():
    return {"databases": db_manager.list_databases(), "active_db": db_manager.active_db}

@app.post("/api/databases/select")
def select_database(req: SelectDbRequest):
    success = db_manager.set_active_db(req.db_name)
    if not success:
        raise HTTPException(status_code=404, detail="Database not found")
    return {"success": True, "active_db": db_manager.active_db}

@app.get("/api/schema")
def get_schema(db_name: Optional[str] = None):
    schema = db_manager.get_schema(db_name)
    return schema

@app.post("/api/query/natural")
def analyze_natural_language(req: NaturalQueryRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    result = sql_agent.run_analyst_pipeline(
        question=req.question.strip(),
        db_name=req.db_name,
        provider=req.provider or "offline",
        api_key=req.api_key,
        model=req.model,
        base_url=req.base_url,
        simulate_error=bool(req.simulate_error),
        max_retries=req.max_retries or 3
    )
    return result

@app.post("/api/query/sql")
def execute_sql(req: RawSqlRequest):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    res = db_manager.execute_query(req.query, db_name=req.db_name, allow_mutation=req.allow_mutation)
    return res

@app.post("/api/query/explain")
def explain_sql(req: RawSqlRequest):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    res = db_manager.explain_query(req.query, db_name=req.db_name)
    return res

@app.post("/api/upload/db")
async def upload_database(file: UploadFile = File(...)):
    filename = file.filename
    if not filename.endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=400, detail="Only .db, .sqlite, and .sqlite3 files are supported")
    
    clean_name = os.path.basename(filename)
    dest_path = os.path.join(DATA_DIR, clean_name)
    
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db_manager.set_active_db(clean_name)
    return {"success": True, "message": f"Database {clean_name} uploaded successfully", "active_db": clean_name}

@app.post("/api/upload/csv")
async def upload_csv(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    db_name: Optional[str] = Form(None)
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")
    
    temp_path = os.path.join(DATA_DIR, f"temp_{file.filename}")
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    success, msg = db_manager.import_csv(temp_path, table_name=table_name, db_name=db_name)
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@app.post("/api/databases/reset")
def reset_databases():
    seed_data.seed_ecommerce()
    seed_data.seed_company_hr()
    seed_data.seed_healthcare()
    db_manager.set_active_db("ecommerce.db")
    return {"success": True, "message": "All sample databases reset to initial state"}

@app.get("/api/prompts")
def get_sample_prompts():
    return {
        "ecommerce.db": [
            {"label": "Top Spenders", "prompt": "Show top 5 customers by total spending"},
            {"label": "Category Breakdown", "prompt": "What are the product counts and average prices by category?"},
            {"label": "Order Status & Revenue", "prompt": "What is the total revenue and order count for each order status?"},
            {"label": "Highest Rated Products", "prompt": "Find the highest rated products with their price and stock"},
            {"label": "Payment Methods", "prompt": "Which payment methods are most frequently used?"},
            {"label": "Sales by City", "prompt": "Show sales and order counts grouped by shipping city"}
        ],
        "company_hr.db": [
            {"label": "Salary by Dept", "prompt": "Which department has the highest average salary?"},
            {"label": "Remote vs Hybrid", "prompt": "Compare employee counts and salaries across remote statuses"},
            {"label": "Top Performers", "prompt": "Show employees with performance ratings of 4.7 or higher"},
            {"label": "Project Budgets", "prompt": "List all active projects with their allocated budget and department"}
        ],
        "healthcare.db": [
            {"label": "Doctor Experience", "prompt": "List all doctors ordered by years of experience and consultation fee"},
            {"label": "Top Diagnoses", "prompt": "What are the most frequent diagnoses and their average billing amount?"},
            {"label": "Insurance Providers", "prompt": "Count of patients per insurance provider"},
            {"label": "Recent Appointments", "prompt": "Show recent appointments with patient names, doctor names, and diagnosis"}
        ]
    }

# Mount frontend files
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
