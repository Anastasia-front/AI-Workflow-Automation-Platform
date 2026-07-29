from types import SimpleNamespace

from app.services.rag import RAGService


def _chunk(document_id, document_name, score, chunk_id):
    return SimpleNamespace(
        document_id=document_id,
        document_name=document_name,
        score=score,
        chunk_id=chunk_id,
    )


def _rag_service():
    return RAGService(
        retrieval_service=SimpleNamespace(),
        ai_service=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
    )


def test_build_sources_drops_chunks_below_relevance_threshold():
    service = _rag_service()
    chunks = [
        _chunk(1, "strong-match.txt", score=0.1, chunk_id=1),
        _chunk(2, "weak-match.txt", score=0.5, chunk_id=2),
    ]

    sources = service.build_sources(chunks)

    document_names = {source["document_name"] for source in sources}
    assert "strong-match.txt" in document_names
    assert "weak-match.txt" not in document_names


def test_build_sources_counts_only_relevant_matches_per_document():
    service = _rag_service()
    chunks = [
        _chunk(1, "doc.txt", score=0.05, chunk_id=1),
        _chunk(1, "doc.txt", score=0.1, chunk_id=2),
        _chunk(1, "doc.txt", score=0.5, chunk_id=3),
    ]

    sources = service.build_sources(chunks)

    assert len(sources) == 1
    assert sources[0]["matches"] == 2


def test_build_sources_caps_to_top_documents_by_relevance():
    service = _rag_service()
    # One clearly dominant document, plus many other documents each with a
    # single coincidental match -- the small-corpus scenario reported by
    # the user, where a fixed distance threshold alone let through ~15
    # barely-relevant documents.
    chunks = [_chunk(0, "best-match.txt", score=0.02, chunk_id=0)]
    chunks += [
        _chunk(doc_id, f"noise-{doc_id}.txt", score=0.3, chunk_id=100 + doc_id)
        for doc_id in range(1, 15)
    ]
    # A document with many weak matches shouldn't outrank the single
    # strongest match either.
    chunks += [
        _chunk(99, "many-weak-matches.txt", score=0.34, chunk_id=200 + i)
        for i in range(13)
    ]

    sources = service.build_sources(chunks)

    assert len(sources) == 3
    assert sources[0]["document_name"] == "best-match.txt"
    assert "many-weak-matches.txt" not in {s["document_name"] for s in sources}
