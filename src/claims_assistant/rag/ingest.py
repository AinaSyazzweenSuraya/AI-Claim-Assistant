import hashlib
import json
from pathlib import Path

from claims_assistant.config import Settings
from claims_assistant.rag.chunking import chunks
from claims_assistant.rag.embeddings import embed
from claims_assistant.rag.vector_store import VectorStore
from claims_assistant.services.policy_rules import PolicyRules


def source_documents(root: Path) -> list[tuple[dict, Path]]:
    manifest = json.loads((root / "data/policies/policy_manifest.json").read_text(encoding="utf-8"))
    documents = []
    for policy in manifest["policies"]:
        for name in policy["documents"]:
            path = (root / "data/policies" / name).resolve()
            if not path.is_relative_to((root / "data/policies").resolve()):
                raise ValueError("Policy document must stay in data/policies")
            documents.append((policy, path))
    return documents


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [p for _, p in source_documents(root)]
    paths += [root / "data/policies/policy_manifest.json"]
    paths += sorted((root / "data/rules").glob("*.json"))
    for path in sorted(set(paths)):
        digest.update(str(path.relative_to(root.resolve())).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def ingest(settings: Settings) -> int:
    PolicyRules(settings.root)  # Verify version metadata before indexing.
    indexed = []
    for policy, path in source_documents(settings.root):
        metadata = {
            "policy_id": policy["id"],
            "version": policy["version"],
            "effective_from": policy["effective_from"],
            "effective_to": policy["effective_to"],
            "source": str(path.relative_to(settings.root.resolve())),
        }
        for chunk in chunks(path.read_text(encoding="utf-8"), metadata):
            chunk["embedding"] = embed(chunk["section"] + " " + chunk["text"])
            indexed.append(chunk)
    VectorStore(settings.runtime / "vector_index/policies.json").write(
        {"format": 1, "source_digest": source_digest(settings.root), "chunks": indexed}
    )
    return len(indexed)
