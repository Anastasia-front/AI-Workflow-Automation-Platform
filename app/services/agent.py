from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.core import (
    DELEGATION_FAILURE_PHRASES,
    DOCUMENT_LIST_TERMS,
    DOCUMENT_REFERENCE_TERMS,
)
from app.enums import DocumentStatus
from app.models import Project
from app.prompts import RAGPromptBuilder
from app.repositories import DocumentRepository
from app.services.ai import AIService
from app.services.rag import RAGService
from app.services.workspace_tools import WorkspaceToolRegistry


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
        normalized = question.lower()

        if self._is_embedding_update_request(normalized):
            result = await self.workspace_tools.update_files_for_embedding_model(
                db,
                project_id=project_id,
            )
            return self._format_embedding_update_result(result.data)

        if "embedding" in normalized and any(
            term in normalized
            for term in ("check", "status", "need", "requires", "mismatch")
        ):
            result = await self.workspace_tools.check_embedding_rebuild_need(
                db,
                project_id=project_id,
            )
            return self._format_embedding_check_result(result.data)

        if any(
            term in normalized
            for term in (
                "process documents",
                "process uploaded",
                "process all documents",
            )
        ):
            return await self._process_project_documents(db=db, project_id=project_id)

        if "sync" in normalized and "embedding" in normalized:
            project = await db.get(Project, project_id)
            result = await self.workspace_tools.sync_project_embeddings(
                db, project=project
            )
            return self._format_tool_result(result)

        if "list" in normalized and "workflow" in normalized:
            result = await self.workspace_tools.list_workflows(
                db, project_id=project_id
            )
            return self._format_workflows(result.data)

        if "create" in normalized and "workflow" in normalized:
            workflow_name = self._workflow_name_from_question(question)
            created = await self.workspace_tools.create_workflow(
                db,
                project_id=project_id,
                name=workflow_name,
            )
            steps = []
            step_ids_by_order = {}
            for definition in self._workflow_steps_from_question(question):
                depends_on = [
                    step_ids_by_order[order]
                    for order in definition.get("depends_on_orders", [])
                    if order in step_ids_by_order
                ]
                step = await self.workspace_tools.create_workflow_step(
                    db,
                    workflow_id=created.data["id"],
                    name=definition["name"],
                    prompt_template=definition["prompt_template"],
                    step_order=definition["step_order"],
                    depends_on=depends_on,
                )
                steps.append(step.data)
                step_ids_by_order[definition["step_order"]] = step.data["id"]
            step_names = ", ".join(f"`{step['name']}`" for step in steps)
            return (
                "Workspace Agent created a workflow.\n\n"
                f"- Workflow: `{created.data['name']}` (id: {created.data['id']})\n"
                f"- Steps: {step_names}\n\n"
                "Run it explicitly with a target document, for example: "
                "`run workflow Extract invoice fields on invoice.pdf`."
            )

        if "run workflow" in normalized:
            workflows = await self.workspace_tools.list_workflows(
                db, project_id=project_id
            )
            selected = self._select_workflow(question, workflows.data["workflows"])
            if selected is None:
                return "I could not identify which workflow to run. Please include the workflow name or id."
            workflow_input = await self._resolve_workflow_input(
                db=db,
                project_id=project_id,
                question=question,
            )
            if isinstance(workflow_input, str):
                return workflow_input
            result = await self.workspace_tools.run_workflow(
                db,
                workflow_id=selected["id"],
                user_input=workflow_input["input"],
            )
            return (
                f"Workspace tool `run_workflow` queued workflow `{selected['name']}` "
                f"for document `{workflow_input['document'].filename}`.\n\n"
                f"{result.data}"
            )

        if any(
            term in normalized
            for term in ("execution", "workflow run", "failed run", "diagnose")
        ):
            workflows = await self.workspace_tools.list_workflows(
                db, project_id=project_id
            )
            lines = ["Workspace execution summary:"]
            for workflow in workflows.data["workflows"]:
                runs = await self.workspace_tools.list_workflow_runs(
                    db,
                    workflow_id=workflow["id"],
                    user_id=user_id,
                )
                recent = runs.data["runs"][:3]
                lines.append(f"- `{workflow['name']}`: {recent or 'no runs'}")
            return "\n".join(lines)

        return None

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

    def _is_embedding_update_request(self, normalized: str) -> bool:
        return (
            "embedding" in normalized
            and any(
                term in normalized
                for term in ("update", "fit", "new model", "rebuild", "refresh")
            )
            and any(
                term in normalized
                for term in ("file", "files", "document", "documents")
            )
        )

    async def _process_project_documents(
        self,
        *,
        db: AsyncSession,
        project_id: int,
    ) -> str:
        documents = await self.documents.list_for_project(db, project_id)
        queued = []
        skipped = []
        failed = []

        for document in documents:
            if document.status in (
                DocumentStatus.INDEXED,
                DocumentStatus.QUEUED,
                DocumentStatus.PROCESSING,
            ):
                skipped.append(document.filename)
                continue
            try:
                result = await self.workspace_tools.process_document(
                    db, document=document
                )
                if result.status == "queued":
                    queued.append(result.data)
                else:
                    skipped.append(document.filename)
            except Exception as exc:  # noqa: BLE001 - report tool-level failure
                failed.append({"filename": document.filename, "error": str(exc)})

        return (
            "Workspace Agent processed project documents.\n\n"
            f"- Queued: {len(queued)}\n"
            f"- Skipped: {len(skipped)}\n"
            f"- Failed: {len(failed)}\n\n"
            f"Queued items: {queued or 'none'}\n"
            f"Skipped files: {skipped or 'none'}\n"
            f"Failures: {failed or 'none'}"
        )

    def _format_embedding_update_result(self, data: dict) -> str:
        return (
            "Workspace Agent checked the current embedding configuration and queued only required work.\n\n"
            f"- Provider: `{data['embedding_config']['provider']}`\n"
            f"- Model: `{data['embedding_config']['model']}`\n"
            f"- Dimensions: `{data['embedding_config']['dimensions']}`\n"
            f"- Queued rebuilds: {len(data['queued_rebuilds'])}\n"
            f"- Already current: {len(data['already_current'])}\n"
            f"- Active jobs skipped: {len(data['active_jobs'])}\n"
            f"- Not ready skipped: {len(data['not_ready'])}\n"
            f"- Failed queue attempts: {len(data['failed'])}\n\n"
            f"Queued: {self._format_document_items(data['queued_rebuilds'])}\n"
            f"Already current: {self._format_document_items(data['already_current'])}\n"
            f"Active jobs: {self._format_document_items(data['active_jobs'])}\n"
            f"Not ready: {self._format_document_items(data['not_ready'])}\n"
            f"Failed: {data['failed'] or 'none'}"
        )

    def _format_embedding_check_result(self, data: dict) -> str:
        classification = data["classification"]
        return (
            "Workspace Agent inspected document embedding metadata.\n\n"
            f"- Current: {len(classification['current'])}\n"
            f"- Rebuild required: {len(classification['rebuild_required'])}\n"
            f"- Missing embeddings: {len(classification['missing_embeddings'])}\n"
            f"- Failed: {len(classification['failed'])}\n"
            f"- Unknown metadata: {len(classification['unknown_metadata'])}\n"
            f"- Active jobs: {len(classification['active_jobs'])}\n"
            f"- Not ready: {len(classification['not_ready'])}"
        )

    def _format_tool_result(self, result) -> str:
        return (
            f"Workspace tool `{result.tool}` finished with status `{result.status}`.\n\n"
            f"{result.data}"
        )

    def _format_workflows(self, data: dict) -> str:
        workflows = data["workflows"]
        if not workflows:
            return "No workflows exist in this project."
        lines = ["Project workflows:"]
        for workflow in workflows:
            lines.append(
                f"- `{workflow['name']}` (id: {workflow['id']}, status: {workflow['status']})"
            )
        return "\n".join(lines)

    def _format_document_items(self, items: list[dict]) -> str:
        if not items:
            return "none"
        return ", ".join(f"`{item.get('filename', item.get('id'))}`" for item in items)

    def _workflow_name_from_question(self, question: str) -> str:
        normalized = question.strip().rstrip(".")
        if "workflow that" in normalized.lower():
            return normalized.lower().split("workflow that", 1)[1].strip().capitalize()
        if "workflow to" in normalized.lower():
            return normalized.lower().split("workflow to", 1)[1].strip().capitalize()
        return "Workspace generated workflow"

    def _workflow_prompt_from_question(self, question: str) -> str:
        return (
            "Complete this workflow task using the provided input.\n\n"
            f"Task: {question}\n\n"
            "Input:\n{{input}}\n\n"
            "Return a structured, concise result."
        )

    def _workflow_steps_from_question(self, question: str) -> list[dict]:
        normalized = question.lower()
        if "invoice" in normalized and any(
            term in normalized for term in ("extract", "field", "fields")
        ):
            return [
                {
                    "step_order": 1,
                    "name": "Extract invoice fields",
                    "prompt_template": (
                        "You are extracting fields from an invoice document.\n\n"
                        "Invoice document text:\n{{input}}\n\n"
                        "Extract the actual values present in the document. "
                        "Return strict JSON with keys: invoice_number, invoice_date, "
                        "customer_name, vendor_name, address, city, state, zip, country, "
                        "order_number, order_date, total_amount, payment_method, due_date, "
                        "line_items, warnings. Use null when a value is missing. "
                        "Do not describe a workflow."
                    ),
                },
                {
                    "step_order": 2,
                    "name": "Validate invoice fields",
                    "prompt_template": (
                        "Validate and clean the extracted invoice JSON.\n\n"
                        "Original invoice text:\n{{input}}\n\n"
                        "Previous step outputs:\n{{dependency_outputs}}\n\n"
                        "Return final JSON with corrected values, confidence notes, "
                        "and warnings for missing or ambiguous fields. Do not describe a workflow."
                    ),
                    "depends_on_orders": [1],
                },
            ]

        return [
            {
                "step_order": 1,
                "name": "Analyze input",
                "prompt_template": self._workflow_prompt_from_question(question),
            }
        ]

    async def _resolve_workflow_input(
        self,
        *,
        db: AsyncSession,
        project_id: int,
        question: str,
    ) -> dict | str:
        documents = [
            document
            for document in await self.documents.list_for_project(db, project_id)
            if document.status == DocumentStatus.INDEXED
            and (document.text or "").strip()
        ]

        if not documents:
            return (
                "I cannot run this workflow yet because no indexed document text is "
                "available in the project. Upload and process a document first."
            )

        selected = self._select_document(question, documents)
        if selected is None:
            available = ", ".join(f"`{document.filename}`" for document in documents)
            return (
                "Which document should I run this workflow on? Available indexed "
                f"documents: {available}"
            )

        return {
            "document": selected,
            "input": (f"Document filename: {selected.filename}\n\n" f"{selected.text}"),
        }

    def _select_document(self, question: str, documents: list) -> object | None:
        normalized = question.lower()
        for document in documents:
            filename = document.filename.lower()
            stem = filename.rsplit(".", 1)[0]
            if filename in normalized or stem in normalized:
                return document

        if "invoice" in normalized:
            invoice_documents = [
                document
                for document in documents
                if "invoice" in document.filename.lower()
            ]
            if len(invoice_documents) == 1:
                return invoice_documents[0]

        if len(documents) == 1:
            return documents[0]

        return None

    def _select_workflow(self, question: str, workflows: list[dict]) -> dict | None:
        normalized = question.lower()
        for workflow in workflows:
            if (
                str(workflow["id"]) in normalized
                or workflow["name"].lower() in normalized
            ):
                return workflow
        if len(workflows) == 1:
            return workflows[0]
        return None

    def _needs_project_documents(self, question: str, history: list[dict]) -> bool:
        normalized = question.lower()
        if any(term in normalized for term in DOCUMENT_REFERENCE_TERMS):
            return True

        return any(
            self._has_document_thread_context(message) for message in history[-8:]
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
