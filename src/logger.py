"""
Diagnostic Structured Logger for Text-to-SQL Analyst AI.
Provides:
- Event tracking (QUERY_RECEIVED, SCHEMA_BUILT, AMBIGUITY_DETECTED, LLM_CALLED, SQL_GENERATED, VALIDATION_PASSED, VALIDATION_FAILED, DB_EXECUTED, DB_ERROR, RETRY_ATTEMPT, PIPELINE_COMPLETED).
- Automatic redaction of secrets, API keys, Bearer tokens, and local file paths.
- In-memory ring buffer for observability in UI and tests.
"""

import os
import re
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

# Standard Python logger
logger = logging.getLogger("text2sql_analyst")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [Text2SQL] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def redact_sensitive_info(text: str) -> str:
    """
    Redacts API keys, Authorization headers, Bearer tokens,
    and absolute file paths from logging strings.
    """
    if not text:
        return ""
    
    redacted = str(text)

    # Redact Authorization Bearer headers first
    redacted = re.sub(r"(Bearer\s+)[A-Za-z0-9\.\-_]{15,}", r"\1[REDACTED_TOKEN]", redacted, flags=re.IGNORECASE)

    # Redact API keys / tokens (e.g. sk-..., AIzaSy..., key=...)
    redacted = re.sub(r"(AIzaSy[A-Za-z0-9\-_]{20,})", r"[REDACTED_GEMINI_KEY]", redacted)
    redacted = re.sub(r"(sk-[A-Za-z0-9\-_]{20,})", r"[REDACTED_OPENAI_KEY]", redacted)
    redacted = re.sub(r"([?&]key=)[A-Za-z0-9\-_]+", r"\1[REDACTED_KEY]", redacted)


    # Redact Windows and Unix absolute paths
    redacted = re.sub(r"[A-Za-z]:\\[\w\\\.\s\-_]+", "<local_path>", redacted)
    redacted = re.sub(r"/(?:home|Users|var|tmp|app)/[\w\./\-_]+", "<local_path>", redacted)

    return redacted

@dataclass
class DiagnosticEvent:
    timestamp: str
    event_type: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None

class ObservabilityManager:
    """Maintains an in-memory buffer of diagnostic events for pipeline observability."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._events = []
            cls._instance._max_size = 200
        return cls._instance

    def log_event(
        self,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None
    ) -> DiagnosticEvent:
        safe_message = redact_sensitive_info(message)
        safe_details = {}
        if details:
            for k, v in details.items():
                if isinstance(v, str):
                    safe_details[k] = redact_sensitive_info(v)
                else:
                    safe_details[k] = v

        event = DiagnosticEvent(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            event_type=event_type,
            message=safe_message,
            details=safe_details,
            duration_ms=duration_ms
        )

        self._events.append(event)
        if len(self._events) > self._max_size:
            self._events.pop(0)

        logger.info(f"[{event_type}] {safe_message}" + (f" ({duration_ms}ms)" if duration_ms else ""))
        return event

    def get_events(self, limit: int = 50) -> List[DiagnosticEvent]:
        return list(self._events[-limit:])

    def clear(self) -> None:
        self._events.clear()

observability = ObservabilityManager()
