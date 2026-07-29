from app.repositories import RetrievalRepository
from app.schemas import RetrievalResponse, RetrievalResult
from app.services.embedding import EmbeddingService


class RetrievalService:

    def __init__(
        self,
        retrieval_repository: RetrievalRepository,
        embedding_service: EmbeddingService,
    ):
        self.repository = retrieval_repository
        self.embedding_service = embedding_service

    async def retrieve(
        self,
        db,
        *,
        project_id: int,
        user_id: int,
        query: str,
        top_k: int = 5,
    ) -> RetrievalResponse:

        query_embedding = await self.embedding_service.embed_text(query)

        rows = await self.repository.search(
            db=db,
            project_id=project_id,
            user_id=user_id,
            embedding=query_embedding,
            provider=self.embedding_service.provider,
            model_name=self.embedding_service.model_name,
            top_k=top_k,
        )

        return RetrievalResponse(
            results=[
                RetrievalResult(
                    document_id=chunk.document_id,
                    document_name=document_name,
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    score=float(score),
                    text=chunk.text,
                )
                for chunk, document_name, score in rows
            ]
        )
