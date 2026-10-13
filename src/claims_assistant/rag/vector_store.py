import json
import os
import tempfile
from pathlib import Path


class VectorStore:
    def __init__(self, path: Path):
        self.path = path

    def write(self, document: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as stream:
            json.dump(document, stream)
            temporary = stream.name
        os.replace(temporary, self.path)

    def read(self) -> dict:
        if not self.path.exists():
            raise ValueError("Policy index missing; run claims ingest")
        return json.loads(self.path.read_text())
