from datetime import date

from claims_assistant.config import Settings
from claims_assistant.rag.retrieval import retrieve
from claims_assistant.schemas.tool_result import ToolResult


def search_policy(settings: Settings, query: str, expense_date: date) -> ToolResult:
    return ToolResult.success(retrieve(settings, query, expense_date))
