"""Small offline lexical retriever for archive evidence, without model calls."""
import math
import re
from collections import Counter
from datetime import datetime, time
from zoneinfo import ZoneInfo


def _vector(text):
    text = re.sub(r"\s+", "", text or "").casefold()
    return Counter(text[index:index + 2] for index in range(max(0, len(text) - 1)))


def top_documents(query, documents, k=3):
    if k < 1:
        raise ValueError("k must be positive")
    vectors = [_vector(doc["text"]) for doc in documents]
    frequencies = Counter(term for vector in vectors for term in vector)
    idf = {term: math.log((len(documents) + 1) / (count + 1)) + 1 for term, count in frequencies.items()}
    q = {term: count * idf.get(term, 1.0) for term, count in _vector(query).items()}
    qnorm = math.sqrt(sum(value * value for value in q.values()))
    ranked = []
    for doc, vector in zip(documents, vectors):
        v = {term: count * idf[term] for term, count in vector.items()}
        norm = math.sqrt(sum(value * value for value in v.values()))
        score = sum(value * q.get(term, 0) for term, value in v.items()) / (norm * qnorm) if norm and qnorm else 0.0
        ranked.append((score, doc["id"], doc))
    return [doc for _, _, doc in sorted(ranked, key=lambda item: (-item[0], item[1]))[:k]]


def known_by(published_at, as_of):
    """Date-only evidence cannot establish same-day intraday availability."""
    try:
        pub, end = str(published_at), str(as_of)
        zone = ZoneInfo("Asia/Shanghai")
        if len(pub) == 10 and len(end) > 10 and pub == end[:10]:
            return False
        p = datetime.fromisoformat(pub)
        cutoff = datetime.fromisoformat(end)
        if len(end) == 10:
            cutoff = datetime.combine(cutoff.date(), time.max)
        if p.tzinfo is None:
            p = p.replace(tzinfo=zone)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=zone)
        return p <= cutoff
    except (TypeError, ValueError):
        return False
