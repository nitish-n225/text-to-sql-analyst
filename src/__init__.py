"""
Text-to-SQL Analyst AI Package - Stage 2: Advanced Intelligence & Self-Correction
"""

from src.database import DatabaseManager
from src.seeder import seed_sample_database
from src.validator import validate_sql, ValidationResult
from src.schema_context import SchemaContextBuilder
from src.llm_adapter import (
    BaseLLMAdapter,
    DemoModeAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    LLMOutput,
    create_llm_adapter
)
from src.pipeline import TextToSqlPipeline, PipelineResult, AttemptRecord, sanitize_error_context
from src.logger import observability, DiagnosticEvent

__all__ = [
    "DatabaseManager",
    "seed_sample_database",
    "validate_sql",
    "ValidationResult",
    "SchemaContextBuilder",
    "BaseLLMAdapter",
    "DemoModeAdapter",
    "GeminiAdapter",
    "OpenAIAdapter",
    "LLMOutput",
    "create_llm_adapter",
    "TextToSqlPipeline",
    "PipelineResult",
    "AttemptRecord",
    "sanitize_error_context",
    "observability",
    "DiagnosticEvent"
]
