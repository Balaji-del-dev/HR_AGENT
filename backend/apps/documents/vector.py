"""Evidence search over a candidate's masked resume chunks.

Vector search only finds evidence and discovers consented talent-pool
profiles; it never cuts applicants. Scoring combines cosine similarity (when
embeddings exist) with a lexical hit on the criterion's terms, which keeps
search useful when no embedding model is running.

With the pgvector extension installed (VECTOR_BACKEND=auto or pgvector), the
cosine is computed in PostgreSQL over ``embedding::vector``; otherwise in Python.
"""

import math
import re
from collections.abc import Sequence
from functools import lru_cache
from uuid import UUID

from django.conf import settings
from django.db import connection

from apps.documents.models import ResumeChunk


@lru_cache(maxsize=1)
def pgvector_available() -> bool:
    if settings.VECTOR_BACKEND == "python":
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        installed = cursor.fetchone() is not None
    if settings.VECTOR_BACKEND == "pgvector" and not installed:
        raise RuntimeError("VECTOR_BACKEND=pgvector but the vector extension is not installed.")
    return installed


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _terms(query: str, extra_terms: Sequence[str]) -> list[str]:
    terms = [t.lower() for t in [query, *extra_terms] if t and t.strip()]
    return list(dict.fromkeys(terms))


def lexical_score(text: str, terms: Sequence[str]) -> float:
    lowered = text.lower()
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered):
            return 1.0
    return 0.0


def search_candidate_chunks(
    *,
    candidate_id: UUID,
    query: str,
    query_embedding: Sequence[float] | None,
    embedding_model: str = "",
    extra_terms: Sequence[str] = (),
    k: int = 4,
) -> list[tuple[ResumeChunk, float]]:
    """Top-k chunks for one candidate. Runs under the active tenant (RLS applies).

    Cosine is only computed against chunks embedded by the same model as the query.
    """
    chunks = list(ResumeChunk.objects.filter(candidate_id=candidate_id).order_by("document", "position"))
    terms = _terms(query, extra_terms)
    sims: dict[UUID, float] = {}
    comparable = [c for c in chunks if c.embedding and c.embedding_model == embedding_model]
    if query_embedding is not None and comparable:
        if pgvector_available():
            sims = _pgvector_similarities([c.id for c in comparable], query_embedding)
        else:
            sims = {c.id: cosine(c.embedding or [], query_embedding) for c in comparable}
    scored = [(chunk, sims.get(chunk.id, 0.0) + 0.5 * lexical_score(chunk.content_masked, terms)) for chunk in chunks]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]


def _pgvector_similarities(chunk_ids: list[UUID], query_embedding: Sequence[float]) -> dict[UUID, float]:
    literal = "[" + ",".join(f"{value:.6f}" for value in query_embedding) + "]"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, 1 - (embedding::vector <=> %s::vector) FROM documents_resumechunk "
            "WHERE id = ANY(%s) AND embedding IS NOT NULL",
            [literal, chunk_ids],
        )
        return {row[0]: float(row[1]) for row in cursor.fetchall()}


def rank_candidates(
    *,
    candidate_ids: Sequence[UUID],
    query: str,
    query_embedding: Sequence[float] | None,
    embedding_model: str = "",
    extra_terms: Sequence[str] = (),
) -> list[tuple[UUID, float]]:
    """Best chunk score per candidate, for talent-pool discovery."""
    best: dict[UUID, float] = {}
    for candidate_id in candidate_ids:
        top = search_candidate_chunks(
            candidate_id=candidate_id,
            query=query,
            query_embedding=query_embedding,
            embedding_model=embedding_model,
            extra_terms=extra_terms,
            k=1,
        )
        if top:
            best[candidate_id] = top[0][1]
    return sorted(best.items(), key=lambda pair: pair[1], reverse=True)
