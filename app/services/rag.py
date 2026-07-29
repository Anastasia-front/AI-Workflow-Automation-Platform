from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import MAX_SOURCES, SIMILARITY_THRESHOLD, SOURCE_RELEVANCE_THRESHOLD
from app.prompts import RAGPromptBuilder
from app.services.ai import AIService
from app.services.retrieval import RetrievalService


class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        ai_service: AIService,
        prompt_builder: RAGPromptBuilder,
    ) -> None:
        self.retrieval = retrieval_service
        self.ai = ai_service
        self.prompts = prompt_builder

    async def answer(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        user_id: int,
        question: str,
        history: list[dict],
        system_prompt: str,
        top_k: int = 5,
    ) -> tuple[str, list[dict]]:

        filtered_results = await self.search_project_documents(
            db=db,
            project_id=project_id,
            user_id=user_id,
            queries=[question],
            top_k=top_k,
        )

        context = self.prompts.build_context(filtered_results)

        rag_system_prompt = self.prompts.build_system_prompt(
            base_prompt=system_prompt,
            context=context,
        )

        answer = await self.ai.generate_chat_response(
            messages=history,
            system_prompt=rag_system_prompt,
        )

        sources = self.build_sources(filtered_results)

        return answer, sources

    async def search_project_documents(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        user_id: int,
        queries: list[str],
        top_k: int = 5,
    ) -> list:
        filtered_results = []
        seen_chunks = set()

        for query in queries:
            retrieved = await self.retrieval.retrieve(
                db=db,
                project_id=project_id,
                user_id=user_id,
                query=query,
                top_k=top_k,
            )

            for result in retrieved.results:
                if result.score > SIMILARITY_THRESHOLD:
                    continue

                if result.chunk_id in seen_chunks:
                    continue

                seen_chunks.add(result.chunk_id)
                filtered_results.append(result)

        return filtered_results

    def build_sources(
        self,
        chunks,
    ) -> list[dict]:
        # SIMILARITY_THRESHOLD (applied earlier, in search_project_documents)
        # decides what's loosely relevant enough to feed the LLM as answer
        # context. Citing a source to the user is a stricter claim, so only
        # confidently-relevant chunks are surfaced here.
        relevant_chunks = [
            chunk for chunk in chunks if chunk.score <= SOURCE_RELEVANCE_THRESHOLD
        ]

        grouped = defaultdict(list)

        for chunk in relevant_chunks:
            grouped[
                (
                    chunk.document_id,
                    chunk.document_name,
                )
            ].append(chunk)

        sources = []

        for (
            document_id,
            document_name,
        ), matches in grouped.items():

            sources.append(
                {
                    "document_id": document_id,
                    "document_name": document_name,
                    "matches": len(matches),
                    "best_score": min(m.score for m in matches),
                }
            )

        sources.sort(key=lambda s: s["best_score"])
        return sources[:MAX_SOURCES]


# The flow is now:

# Retrieved chunks
#         ↓
# Threshold filter
#         ↓
# filtered_results
#         ↓
# Context builder
#         ↓
# LLM answer

# filtered_results
#         ↓
# _build_sources()
#         ↓
# deduplicated documents
#         ↓
# frontend citations
