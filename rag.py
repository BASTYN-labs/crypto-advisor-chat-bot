"""
RAG retrieval module for the crypto advisor.
Provides contextually relevant investment persona knowledge for the advisor.
"""
import math
import logging
import os

logging.basicConfig(
    filename="app.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)

PERSONAS_FILE = os.path.join(os.path.dirname(__file__), "personas.txt")


def load_corpus() -> list[dict]:
    with open(PERSONAS_FILE, "r") as f:
        raw = f.read()

    chunks = []
    current = []
    for line in raw.splitlines():
        current.append(line)
        if line.startswith("PERSONA:") and current:
            chunks.append("\n".join(current[:-1]))
            current = [line]
    if current:
        chunks.append("\n".join(current))

    return [{"id": i, "text": c} for i, c in enumerate(chunks) if c.strip()]


def _tf_idf_score(query: str, text: str) -> float:
    query_terms = set(query.lower().split())
    text_terms = text.lower().split()
    if not text_terms:
        return 0.0
    freq = sum(1 for t in text_terms if t in query_terms)
    return freq / math.sqrt(len(text_terms))


def retrieve(query: str, top_k: int = 3) -> list[str]:
    corpus = load_corpus()
    scored = [(chunk["text"], _tf_idf_score(query, chunk["text"])) for chunk in corpus]
    scored.sort(key=lambda x: x[1], reverse=True)
    results = [text for text, _ in scored[:top_k]]
    logging.debug("RAG query=%s retrieved=%d chunks", query[:80], len(results))
    return results
