from datetime import date

from claims_assistant.config import Settings
from claims_assistant.rag.embeddings import embed, similarity
from claims_assistant.rag.ingest import source_digest
from claims_assistant.rag.vector_store import VectorStore


def retrieve(settings: Settings, query: str, expense_date: date, limit: int = 3) -> list[dict]:
    index = VectorStore(settings.runtime / "vector_index/policies.json").read()
    if index["source_digest"] != source_digest(settings.root):
        raise ValueError("Policy index is stale; run claims ingest")
    vector = embed(query)
    ranked = []
    for chunk in index["chunks"]:
        if date.fromisoformat(chunk["effective_from"]) > expense_date:
            continue
        if chunk["effective_to"] and expense_date > date.fromisoformat(chunk["effective_to"]):
            continue
        score = similarity(vector, chunk["embedding"])
        if chunk["section"].casefold() in query.casefold().split():
            score += 1  # Exact category heading is stronger than generic policy words.
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]["source"], item[1]["section"]))
    return [
        {**{k: v for k, v in chunk.items() if k != "embedding"}, "score": round(score, 4)}
        for score, chunk in ranked[:limit]
    ]
