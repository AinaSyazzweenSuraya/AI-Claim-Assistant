from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    code: str | None = None
    message: str | None = None

    @classmethod
    def success(cls, data: Any) -> "ToolResult":
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        return cls(ok=True, data=data)

    @classmethod
    def error(cls, code: str, message: str) -> "ToolResult":
        return cls(ok=False, code=code, message=message)
