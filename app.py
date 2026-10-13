"""Vercel FastAPI entry point (configuration is validated at startup)."""

from pathlib import Path

from claims_assistant.interfaces.vercel import create_vercel_app

app = create_vercel_app(Path(__file__).resolve().parent)
