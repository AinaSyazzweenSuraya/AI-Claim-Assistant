from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLAIMS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    root: Path = Path(__file__).resolve().parents[2]
    runtime_dir: Path | None = None
    app_mode: Literal["demo", "private"] = "demo"
    api_token: str = ""
    database_url: SecretStr | None = None
    allowed_hosts: list[str] = ["127.0.0.1", "localhost", "[::1]"]
    llm_mode: Literal["demo", "ollama", "openai"] = "demo"
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = "llama3.2:3b"
    llm_api_key: str = ""
    llm_timeout: float = 120
    receipt_image_backend: Literal["vision", "florence"] = "vision"
    florence_device: Literal["cpu", "cuda"] = "cpu"

    @field_validator("root", "runtime_dir")
    @classmethod
    def absolute_path(cls, value: Path | None) -> Path | None:
        return value.expanduser().resolve() if value else value

    @property
    def runtime(self) -> Path:
        return self.runtime_dir or self.root / "runtime"

    def prepare(self) -> None:
        if self.app_mode == "private" and not self.api_token:
            raise ValueError("Private mode requires CLAIMS_API_TOKEN")
        for name in ["uploads", "vector_index", "logs"]:
            (self.runtime / name).mkdir(parents=True, exist_ok=True)
