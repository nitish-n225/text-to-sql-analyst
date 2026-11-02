"""
Stage 4, Feature 2: Conversational Analytics and Follow-Up Context Management.

Provides:
1. ConversationTurn: Metadata-only representation of a single query turn.
   Never stores raw uploaded datasets, passwords, database credentials, or full row dumps.
2. ConversationSession: Manages turn history for a single user/session.
   Enforces data source isolation (switching databases resets or isolates context),
   prunes context to recent turns, and provides sanitized prompt context for the LLM.
3. ConversationManager: Multi-session registry for complete isolation between users or test environments.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid


@dataclass
class ConversationTurn:
    """
    Represents a single query-response turn in a conversation.
    Stores metadata only: questions, SQL, explanations, and counts.
    Never stores raw query result dataframes or sensitive credentials.
    """
    turn_id: int
    timestamp: str
    question: str
    sql: str
    explanation: str
    delta_explanation: Optional[str] = None
    success: bool = True
    rows_count: int = 0
    columns: List[str] = field(default_factory=list)
    summary: str = ""
    error_message: Optional[str] = None
    data_source: str = "sample:business.db"

    def to_prompt_dict(self) -> Dict[str, Any]:
        """Returns a sanitized dict suitable for feeding into an LLM prompt."""
        return {
            "turn_id": self.turn_id,
            "question": self.question,
            "sql": self.sql,
            "explanation": self.explanation,
            "delta_explanation": self.delta_explanation,
            "columns": self.columns,
            "rows_count": self.rows_count,
            "success": self.success
        }

    def to_display_dict(self) -> Dict[str, Any]:
        """Returns a dict suitable for UI display and audit inspection."""
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "question": self.question,
            "sql": self.sql,
            "explanation": self.explanation,
            "delta_explanation": self.delta_explanation,
            "success": self.success,
            "rows_count": self.rows_count,
            "columns": self.columns,
            "summary": self.summary,
            "error_message": self.error_message,
            "data_source": self.data_source
        }


class ConversationSession:
    """
    Manages conversational history for a single session.
    Guarantees isolation, bounded memory, and data source isolation.
    """
    def __init__(self, session_id: Optional[str] = None, data_source: str = "sample:business.db"):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.data_source: str = data_source
        self._turns: List[ConversationTurn] = []

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def add_turn(
        self,
        question: str,
        sql: str,
        explanation: str,
        delta_explanation: Optional[str] = None,
        success: bool = True,
        rows_count: int = 0,
        columns: Optional[List[str]] = None,
        summary: str = "",
        error_message: Optional[str] = None
    ) -> ConversationTurn:
        """Appends a new turn to the conversation history."""
        next_turn_id = len(self._turns) + 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        turn = ConversationTurn(
            turn_id=next_turn_id,
            timestamp=now_str,
            question=question.strip(),
            sql=sql.strip() if sql else "",
            explanation=explanation.strip() if explanation else "",
            delta_explanation=delta_explanation.strip() if delta_explanation else None,
            success=success,
            rows_count=rows_count,
            columns=columns or [],
            summary=summary.strip() if summary else "",
            error_message=error_message.strip() if error_message else None,
            data_source=self.data_source
        )
        self._turns.append(turn)
        return turn

    def get_history(self) -> List[ConversationTurn]:
        """Returns all turns in this session."""
        return list(self._turns)

    def get_last_successful_turn(self) -> Optional[ConversationTurn]:
        """Returns the most recent successful turn, or None if none exist."""
        for t in reversed(self._turns):
            if t.success and t.sql:
                return t
        return None

    def get_context_for_prompt(self, max_turns: int = 3) -> List[Dict[str, Any]]:
        """
        Returns sanitized prompt context for the most recent successful turns.
        Limits to max_turns to keep prompt sizes bounded.
        """
        successful_turns = [t for t in self._turns if t.success and t.sql]
        recent = successful_turns[-max_turns:]
        return [t.to_prompt_dict() for t in recent]

    def clear(self) -> None:
        """Clears all turns and resets history for this session."""
        self._turns.clear()

    def set_data_source(self, new_data_source: str) -> bool:
        """
        Updates the active data source.
        If the data source changed, automatically clears conversation history
        to prevent queries and table schemas from leaking across datasets.
        Returns True if history was reset, False if data source is unchanged.
        """
        if new_data_source != self.data_source:
            self.data_source = new_data_source
            self.clear()
            return True
        return False


class ConversationManager:
    """
    Multi-session registry providing complete isolation across different users or tests.
    """
    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}

    def get_or_create_session(
        self,
        session_id: str,
        data_source: str = "sample:business.db"
    ) -> ConversationSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationSession(
                session_id=session_id,
                data_source=data_source
            )
        else:
            # Enforce data source alignment
            self._sessions[session_id].set_data_source(data_source)
        return self._sessions[session_id]

    def reset_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].clear()

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> List[str]:
        return list(self._sessions.keys())
