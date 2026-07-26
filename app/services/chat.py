import json

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import AGENTS
from app.models import Chat, Message
from app.models.user import User
from app.repositories import MessageRepository
from app.services.agent import AgentService
from app.services.ai import AIService
from app.services.exceptions import ResourceConflictError, ResourceNotFoundError
from app.services.rag import RAGService


class ChatService:
    def __init__(
        self,
        messages: MessageRepository,
        rag: RAGService,
        ai: AIService,
        agent_service: AgentService,
    ) -> None:
        self.messages = messages
        self.rag = rag
        self.ai = ai
        self.agent_service = agent_service

    async def create_message(
        self,
        db: AsyncSession,
        *,
        chat: Chat,
        user: User,
        content: str,
        agent_name: str | None = None,
        persist_user_message: bool = True,
    ) -> tuple[Message, Message]:

        # ---------------------------------
        # Save user message
        # ---------------------------------

        if persist_user_message:
            user_message = Message(
                chat_id=chat.id,
                role="user",
                content=content,
            )

            await self.messages.create(
                db,
                user_message,
            )
        else:
            user_message = await self.messages.latest_user_message_for_chat(
                db,
                chat.id,
            )

        # ---------------------------------
        # Conversation history
        # ---------------------------------

        history = await self.messages.list_for_chat(
            db,
            chat.id,
        )

        ollama_messages = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in history
        ]

        # ---------------------------------
        # Agent
        # ---------------------------------

        selected_agent_name = agent_name or chat.agent_name
        agent = AGENTS.get(selected_agent_name)

        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid agent",
            )

        # ---------------------------------
        # Generate answer by selected mode
        # ---------------------------------

        if agent.agentic:
            answer, sources = await self.agent_service.run(
                db=db,
                agent=agent,
                project_id=chat.project_id,
                user_id=user.id,
                question=content,
                history=ollama_messages,
            )
        elif agent.uses_rag:
            answer, sources = await self.rag.answer(
                db=db,
                project_id=chat.project_id,
                user_id=user.id,
                question=content,
                history=ollama_messages,
                system_prompt=agent.system_prompt,
            )
        else:
            answer = await self.ai.generate_chat_response(
                messages=ollama_messages,
                system_prompt=agent.system_prompt,
            )
            sources = []

        # ---------------------------------
        # Save assistant message
        # ---------------------------------

        assistant_message = Message(
            chat_id=chat.id,
            role="assistant",
            content=answer,
            sources=sources,
            provider_used=getattr(self.ai, "last_provider_used", None),
            model_used=getattr(self.ai, "last_model_used", None),
            fallback_used=getattr(self.ai, "last_fallback_used", None),
        )

        await self.messages.create(
            db,
            assistant_message,
        )

        if user_message is None:
            await db.commit()
            await db.refresh(assistant_message)
            return assistant_message, assistant_message

        if persist_user_message:
            return await self.messages.commit_pair(
                db,
                user_message,
                assistant_message,
            )

        await db.commit()
        await db.refresh(assistant_message)
        return user_message, assistant_message

    async def create_message_stream(
        self,
        db: AsyncSession,
        *,
        chat: Chat,
        user: User,
        content: str,
        agent_name: str | None = None,
    ):
        def frame(event: str, payload: dict) -> str:
            return f"event: {event}\ndata: {json.dumps({'event': event, **payload})}\n\n"

        yield frame("queued", {"message": "Message queued"})
        yield frame("started", {"message": "Generating response"})

        try:
            user_message = Message(
                chat_id=chat.id,
                role="user",
                content=content,
            )

            user_message = await self.messages.create_committed(
                db,
                user_message,
            )

            history = await self.messages.list_for_chat(
                db,
                chat.id,
            )

            chat_messages = [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in history
            ]

            selected_agent_name = agent_name or chat.agent_name
            agent = AGENTS.get(selected_agent_name)

            if agent is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid agent",
                )

            answer_chunks = []
            sources = []

            if agent.agentic:
                yield frame("planning", {"message": "Planning document access"})
                answer, sources = await self.agent_service.run(
                    db=db,
                    agent=agent,
                    project_id=chat.project_id,
                    user_id=user.id,
                    question=content,
                    history=chat_messages,
                )
                answer_chunks.append(answer)
                yield frame("token", {"delta": answer})
            elif agent.uses_rag:
                yield frame("retrieval_started", {"message": "Searching project documents"})
                filtered_results = await self.rag.search_project_documents(
                    db=db,
                    project_id=chat.project_id,
                    user_id=user.id,
                    queries=[content],
                    top_k=5,
                )
                sources = self.rag.build_sources(filtered_results)
                yield frame(
                    "retrieval_completed",
                    {
                        "message": "Project document search complete",
                        "source_count": len(sources),
                    },
                )

                context = self.rag.prompts.build_context(filtered_results)
                rag_system_prompt = self.rag.prompts.build_system_prompt(
                    base_prompt=agent.system_prompt,
                    context=context,
                )
                async for chunk in self.ai.stream_chat_response(
                    messages=chat_messages,
                    system_prompt=rag_system_prompt,
                ):
                    answer_chunks.append(chunk)
                    yield frame("token", {"delta": chunk})
            else:
                async for chunk in self.ai.stream_chat_response(
                    messages=chat_messages,
                    system_prompt=agent.system_prompt,
                ):
                    answer_chunks.append(chunk)
                    yield frame("token", {"delta": chunk})

            answer = "".join(answer_chunks)

            assistant_message = Message(
                chat_id=chat.id,
                role="assistant",
                content=answer,
                sources=sources,
                provider_used=getattr(self.ai, "last_provider_used", None),
                model_used=getattr(self.ai, "last_model_used", None),
                fallback_used=getattr(self.ai, "last_fallback_used", None),
            )

            assistant_message = await self.messages.create_committed(
                db,
                assistant_message,
            )
        except Exception as exc:  # noqa: BLE001
            yield frame("failed", {"message": "Message failed", "error": str(exc)})
            return

        yield frame(
            "completed",
            {
                "message": "Response complete",
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
                "content": assistant_message.content,
                "sources": assistant_message.sources or [],
                "provider_used": assistant_message.provider_used,
                "model_used": assistant_message.model_used,
                "fallback_used": assistant_message.fallback_used,
            },
        )

    async def regenerate_message(
        self,
        db: AsyncSession,
        *,
        message_id: int,
        user: User,
    ) -> Message:
        assistant_message = await self.messages.get_for_user(db, message_id, user.id)

        if assistant_message is None or assistant_message.role != "assistant":
            raise ResourceNotFoundError("Assistant message not found")

        chat = await db.get(Chat, assistant_message.chat_id)
        if chat is None:
            raise ResourceNotFoundError("Chat not found")

        user_message = await self.messages.previous_user_message(db, assistant_message)
        if user_message is None:
            raise ResourceConflictError(
                "No user message is available to regenerate from."
            )

        _, new_assistant_message = await self.create_message(
            db=db,
            chat=chat,
            user=user,
            content=user_message.content,
            agent_name=chat.agent_name,
            persist_user_message=False,
        )

        return new_assistant_message


# answer, sources = await self.rag.answer(...)

# That means RAGService should become responsible for the complete RAG pipeline:

# question
#     ↓
# embed query
#     ↓
# retrieve chunks
#     ↓
# build context
#     ↓
# call AIService
#     ↓
# return answer + sources

# So your route doesn't know RAG exists, and ChatService doesn't know how prompts are constructed. Each layer has a single responsibility:

# Route → HTTP.
# ChatService → orchestrates the chat workflow.
# RAGService → retrieval, context construction, citations, and LLM invocation.
# AIService → communicates with Ollama only.

# This separation will make it much easier to add streaming responses,
# multiple retrieval strategies, or workflow-specific context later without changing the route or ChatService
