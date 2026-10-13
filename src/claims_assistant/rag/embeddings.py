"""Offline lexical feature hashing, not a learned semantic embedding model."""

import hashlib
import math
import re
from collections import Counter


def embed(text: str) -> dict[str, float]:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    counts = Counter(hashlib.sha256(token.encode()).hexdigest()[:12] for token in tokens)
    norm = math.sqrt(sum(n * n for n in counts.values())) or 1
    return {token: count / norm for token, count in counts.items()}


def similarity(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(value * b.get(key, 0) for key, value in a.items())
