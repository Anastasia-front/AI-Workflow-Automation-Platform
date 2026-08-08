from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.core import (
    DELEGATION_FAILURE_PHRASES,
    DOCUMENT_LIST_TERMS,
    DOCUMENT_REFERENCE_TERMS,
    settings,
)
from app.prompts import RAGPromptBuilder
from app.repositories import DocumentRepository
from app.services.ai import AIService
from app.services.rag import RAGService
from app.services.workspace_tool_specs import WORKSPACE_TOOL_SPECS
from app.services.workspace_tools import ToolResult, WorkspaceToolRegistry


class AgentService:
    def __init__(
        self,
        *,
        ai: AIService,
        rag: RAGService,
        documents: DocumentRepository,
        workspace_tools: WorkspaceToolRegistry | None = None,
        prompts: RAGPromptBuilder,
    ) -> None:
        self.ai = ai
        self.rag = rag
        self.documents = documents
        self.workspace_tools = workspace_tools
        self.prompts = prompts

    async def run(
        self,
        db: AsyncSession,
        *,
        agent: BaseAgent,
        project_id: int,
        user_id: int,
        question: str,
        history: list[dict],
    ) -> tuple[str, list[dict]]:
        if getattr(agent, "workspace", False) and self.workspace_tools is not None:
            workspace_result = await self._run_workspace_task(
                db=db,
                project_id=project_id,
                user_id=user_id,
                question=question,
            )
            if workspace_result is not None:
                return workspace_result, []

        if self._is_document_listing_request(question):
            return await self._list_project_documents(
                db=db,
                project_id=project_id,
            )

        needs_documents = self._needs_project_documents(question, history)
        retrieval_queries = []
        retrieved_chunks = []
        project_documents = []

        if needs_documents:
            project_documents = await self.documents.list_for_project(db, project_id)
            retrieval_queries = await self._plan_document_searches(
                agent=agent,
                question=question,
                history=history,
                documents=project_documents,
            )
            retrieved_chunks = await self.rag.search_project_documents(
                db=db,
                project_id=project_id,
                user_id=user_id,
                queries=retrieval_queries,
                top_k=8,
            )
            retrieved_chunks = self._with_relevant_document_excerpts(
                question=question,
                retrieved_chunks=retrieved_chunks,
                documents=project_documents,
            )

            if not retrieved_chunks:
                return (
                    "I cannot access relevant uploaded project documents for this ",
                    "request. They may not be uploaded, processed, indexed, or similar ",
                    "enough to the question for retrieval.",
                    [],
                )

        context = self.prompts.build_context(retrieved_chunks)
        system_prompt = self.prompts.build_agent_orchestrator_prompt(
            base_prompt=agent.system_prompt,
            used_document_search=needs_documents,
            context=context,
            retrieval_queries=retrieval_queries,
        )

        answer = await self.ai.generate_chat_response(
            messages=history,
            system_prompt=system_prompt,
        )

        if needs_documents and self._is_delegation_failure(answer):
            answer = await self._retry_final_answer(
                history=history,
                system_prompt=system_prompt,
                question=question,
            )

        return answer, self.rag.build_sources(retrieved_chunks)

    async def _run_workspace_task(
        self,
        *,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        question: str,
    ) -> str | None:
        """Let the model pick and call workspace tools directly, instead of
        matching keywords in `question`.

        Each turn: ask the model for either a final answer or a tool call: if it calls
        a tool, validate the arguments against that tool's Pydantic schema; invalid
        arguments are reported back to the model as a tool result (up to
        WORKSPACE_TOOL_ARGUMENT_MAX_RETRIES times) so it can retry with corrected
        arguments -- the "structured output + retry" pattern applied to tool calls
        instead of a bare JSON response. Returns None (deferring to the normal RAG
        chat path) if the model never calls a workspace tool at all, so this only
        intercepts requests that are actually workspace-management tasks.
        """
        schemas = [spec.to_schema() for spec in WORKSPACE_TOOL_SPECS]
        specs_by_name = {spec.name: spec for spec in WORKSPACE_TOOL_SPECS}
        system_prompt = self._workspace_tool_system_prompt()
        messages: list[dict] = [{"role": "user", "content": question}]
        context = {"project_id": project_id, "user_id": user_id}

        try:
            result = await self.ai.generate_tool_call(
                messages, tools=schemas, system_prompt=system_prompt
            )
        except Exception:  # noqa: BLE001 - no provider could run tool calling; fall back to RAG chat
            return None

        if not result.tool_calls:
            return None

        invalid_argument_attempts = 0

        for _ in range(settings.WORKSPACE_TOOL_MAX_STEPS):
            tool_call = result.tool_calls[0]
            spec = specs_by_name.get(tool_call.name)

            if spec is None:
                tool_result = ToolResult(
                    tool=tool_call.name,
                    status="invalid_tool",
                    data={},
                    message=f"Unknown tool `{tool_call.name}`. Available tools: {', '.join(specs_by_name)}.",
                )
            else:
                try:
                    args = spec.args_model.model_validate(tool_call.arguments)
                except ValidationError as exc:
                    invalid_argument_attempts += 1
                    if invalid_argument_attempts > settings.WORKSPACE_TOOL_ARGUMENT_MAX_RETRIES:
                        return (
                            f"Workspace tool `{spec.name}` kept receiving invalid arguments "
                            f"after {invalid_argument_attempts - 1} retries: {exc.errors()}"
                        )
                    tool_result = ToolResult(
                        tool=spec.name,
                        status="invalid_arguments",
                        data={},
                        message=f"Arguments failed validation: {exc.errors()}. Correct them and call the tool again.",
                    )
                else:
                    invalid_argument_attempts = 0
                    try:
                        tool_result = await spec.invoke(self.workspace_tools, db, context, args)
                    except Exception as exc:  # noqa: BLE001 - surface tool failure to the model, not a crash
                        tool_result = ToolResult(tool=spec.name, status="failed", data={}, message=str(exc))

            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": tool_call.id, "name": tool_call.name, "arguments": tool_call.arguments}
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "content": tool_result.model_dump_json(),
                }
            )

            result = await self.ai.generate_tool_call(
                messages, tools=schemas, system_prompt=system_prompt
            )
            if not result.tool_calls:
                return result.content or "Workspace tool call completed with no further response."

        return "Reached the workspace tool step limit without a final answer."

    def _workspace_tool_system_prompt(self) -> str:
        return (
            "You are the Workspace Agent for an AI automation platform project. "
            "You can call tools to inspect and manage this project's documents, "
            "embeddings, and workflows. Call a tool whenever the user's request maps "
            "to one of the available tools -- including multi-step tasks, where you "
            "should call tools one at a time and use each result to decide the next "
            "call. If the request is a general question that is not about managing "
            "this workspace, respond with plain text and no tool call so it can be "
            "handled by the normal assistant. After your final tool result, give the "
            "user a concise plain-text summary of what happened instead of calling "
            "another tool."
        )

    async def _list_project_documents(
        self,
        *,
        db: AsyncSession,
        project_id: int,
    ) -> tuple[str, list[dict]]:
        documents = await self.documents.list_for_project(db, project_id)

        if not documents:
            return (
                "No uploaded project documents are available for this project.",
                [],
            )

        lines = ["Available project documents:"]
        for document in documents:
            status = getattr(document.status, "value", document.status)
            embedding_status = getattr(
                document.embedding_status,
                "value",
                document.embedding_status,
            )
            lines.append(
                f"- `{document.filename}` "
                f"(status: {status}, embeddings: {embedding_status})"
            )

        return "\n".join(lines), []

    def _needs_project_documents(self, question: str, history: list[dict]) -> bool:
        normalized = question.lower()
        if any(term in normalized for term in DOCUMENT_REFERENCE_TERMS):
            return True

        # Only the user's own recent turns count as thread context -- the
        # assistant's own replies routinely say "document"/"project" while
        # answering a general question, which would otherwise keep RAG
        # switched on for every unrelated follow-up in the conversation.
        recent_user_messages = [
            message for message in history if message.get("role") == "user"
        ][-2:]
        return any(
            self._has_document_thread_context(message)
            for message in recent_user_messages
        )

    def _has_document_thread_context(self, message: dict) -> bool:
        content = (message.get("content") or "").lower()
        return any(term in content for term in DOCUMENT_REFERENCE_TERMS)

    def _is_document_listing_request(self, question: str) -> bool:
        normalized = question.lower()
        mentions_documents = any(
            term in normalized for term in DOCUMENT_REFERENCE_TERMS
        )
        asks_for_list = any(term in normalized for term in DOCUMENT_LIST_TERMS)
        return mentions_documents and asks_for_list

    async def _plan_document_searches(
        self,
        *,
        agent: BaseAgent,
        question: str,
        history: list[dict],
        documents: list,
        max_queries: int = 4,
    ) -> list[str]:
        document_names = "\n".join(f"- {document.filename}" for document in documents)
        planner_prompt = (
            f"{agent.system_prompt}\n\n"
            "You are planning tool calls, not answering the user. "
            "The available tool is search_project_documents(query). "
            f"Return at most {max_queries} newline-separated search queries. "
            "Include specific filenames, document types, entities, and task terms "
            "from the user request when present.\n\n"
            "Available project documents:\n"
            f"{document_names or 'No uploaded documents.'}"
        )

        try:
            planned = await self.ai.generate_chat_response(
                messages=[
                    *history[-6:],
                    {
                        "role": "user",
                        "content": (
                            "Plan document search queries for this request:\n"
                            f"{question}"
                        ),
                    },
                ],
                system_prompt=planner_prompt,
            )
        except Exception:  # noqa: BLE001
            planned = ""

        queries = self._parse_queries(planned, max_queries=max_queries)
        for query in self._document_queries(question, documents):
            if query.lower() not in {item.lower() for item in queries}:
                queries.append(query)

        if question.lower() not in {query.lower() for query in queries}:
            queries.insert(0, question)

        return queries[:max_queries]

    def _document_queries(self, question: str, documents: list) -> list[str]:
        normalized = question.lower()
        queries = []

        for document in self._relevant_documents(normalized, documents):
            queries.append(f"{document.filename} {question}")

        return queries

    def _with_relevant_document_excerpts(
        self,
        *,
        question: str,
        retrieved_chunks: list,
        documents: list,
        max_chars_per_document: int = 3000,
    ) -> list:
        normalized = question.lower()
        existing_document_ids = {
            chunk.document_id
            for chunk in retrieved_chunks
            if hasattr(chunk, "document_id")
        }
        chunks = list(retrieved_chunks)

        for document in self._relevant_documents(normalized, documents):
            if document.id in existing_document_ids:
                continue

            text = (document.text or "").strip()
            if not text:
                continue

            chunks.append(
                SimpleNamespace(
                    document_id=document.id,
                    document_name=document.filename,
                    chunk_id=-document.id,
                    chunk_index=0,
                    score=0.0,
                    text=text[:max_chars_per_document],
                )
            )
            existing_document_ids.add(document.id)

        return chunks

    def _relevant_documents(self, normalized_question: str, documents: list) -> list:
        if not documents:
            return []

        if self._should_explore_all_documents(normalized_question):
            return [document for document in documents if (document.text or "").strip()]

        wants_candidates = any(
            term in normalized_question
            for term in ("candidate", "candidates", "cv", "cvs", "resume", "resumes")
        )
        wants_job = any(
            term in normalized_question
            for term in ("job", "job description", "requirements", "requirement")
        )

        relevant = []
        for document in documents:
            filename = document.filename.lower()
            is_candidate_doc = any(
                term in filename for term in ("candidate", "cv", "resume")
            )
            is_job_doc = any(
                term in filename for term in ("job", "description", "requirement")
            )

            if wants_candidates and is_candidate_doc or wants_job and is_job_doc:
                relevant.append(document)

        return relevant

    def _should_explore_all_documents(self, normalized_question: str) -> bool:
        return any(
            term in normalized_question
            for term in (
                "all",
                "each",
                "every",
                "compare",
                "comparison",
                "analyze",
                "analyse",
                "review",
                "rank",
                "summarize",
                "summarise",
                "highlight",
                "highlights",
                "align",
                "aline",
                "alignment",
            )
        )

    async def _retry_final_answer(
        self,
        *,
        history: list[dict],
        system_prompt: str,
        question: str,
    ) -> str:
        return await self.ai.generate_chat_response(
            messages=[
                *history,
                {
                    "role": "user",
                    "content": (
                        "Your previous draft asked the user to provide or describe "
                        "information that is already in the retrieved project context. "
                        "Redo the answer now. Complete the delegated analysis yourself. "
                        "Do not ask for files, descriptions, pasted text, or manual "
                        "checking. Answer the original request directly:\n"
                        f"{question}"
                    ),
                },
            ],
            system_prompt=system_prompt,
        )

    def _is_delegation_failure(self, answer: str) -> bool:
        normalized = answer.lower()
        return any(phrase in normalized for phrase in DELEGATION_FAILURE_PHRASES)

    def _parse_queries(self, planned: str, *, max_queries: int) -> list[str]:
        queries = []
        seen = set()

        for line in planned.splitlines():
            query = line.strip(" \t-0123456789.").strip()
            if not query:
                continue

            lowered = query.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            queries.append(query)

            if len(queries) >= max_queries:
                break

        return queries
