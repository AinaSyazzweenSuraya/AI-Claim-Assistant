from claims_assistant.config import Settings
from claims_assistant.rag.ingest import ingest

if __name__ == "__main__":
    settings = Settings()
    settings.prepare()
    print(f"Indexed {ingest(settings)} policy sections")
