from pathlib import Path


def load(root: Path, name: str = "agent_instructions.md") -> str:
    if name not in {"agent_instructions.md", "receipt_extraction.md"}:
        raise ValueError("Unknown prompt")
    return (root / "prompts" / name).read_text()
