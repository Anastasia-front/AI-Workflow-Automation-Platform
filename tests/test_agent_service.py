from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.agent import AgentService
from app.services.workspace_tools import ToolResult


@pytest.mark.asyncio
async def test_agent_searches_documents_when_user_references_uploads():
    ai = SimpleNamespace(
        generate_chat_response=AsyncMock(
            side_effect=[
                "requirements\nrisks",
                "Final answer",
            ]
        )
    )
    rag = SimpleNamespace(
        search_project_documents=AsyncMock(return_value=[SimpleNamespace(chunk_id=1)]),
        build_sources=Mock(return_value=[{"document_id": 1}]),
    )
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(
        build_context=Mock(return_value="retrieved context"),
        build_agent_orchestrator_prompt=Mock(return_value="agent prompt"),
    )
    agent = SimpleNamespace(system_prompt="Research agent")

    answer, sources = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="Using uploaded project documents, identify requirements and risks.",
        history=[],
    )

    assert answer == "Final answer"
    assert sources == [{"document_id": 1}]
    rag.search_project_documents.assert_awaited_once()
    prompts.build_agent_orchestrator_prompt.assert_called_once()


@pytest.mark.asyncio
async def test_agent_returns_indexing_message_when_document_search_has_no_results():
    ai = SimpleNamespace(generate_chat_response=AsyncMock(return_value="requirements"))
    rag = SimpleNamespace(
        search_project_documents=AsyncMock(return_value=[]),
        build_sources=Mock(return_value=[]),
    )
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(
        build_context=Mock(return_value=""),
        build_agent_orchestrator_prompt=Mock(return_value="agent prompt"),
    )
    agent = SimpleNamespace(system_prompt="Research agent")

    answer, sources = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="Review the uploaded CVs.",
        history=[],
    )

    assert "cannot access relevant uploaded project documents" in answer
    assert sources == []
    rag.search_project_documents.assert_awaited_once()
    assert ai.generate_chat_response.await_count == 1


@pytest.mark.asyncio
async def test_research_agent_reads_candidate_and_job_docs_when_vector_search_misses():
    ai = SimpleNamespace(
        generate_chat_response=AsyncMock(
            side_effect=[
                "candidate technology highlights\njob requirements",
                "Candidate 01 highlights Python and Django; aligns with backend requirements.",
            ]
        )
    )
    rag = SimpleNamespace(
        search_project_documents=AsyncMock(return_value=[]),
        build_sources=Mock(return_value=[{"document_id": 1}, {"document_id": 2}]),
    )
    documents = SimpleNamespace(
        list_for_project=AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    filename="candidate_01_artem.txt",
                    text="Artem has Python, Django, PostgreSQL, and support experience.",
                ),
                SimpleNamespace(
                    id=2,
                    filename="job_description_senior_support_engineer.txt",
                    text="Requires Python, Django, PostgreSQL, troubleshooting, and support.",
                ),
            ]
        )
    )
    prompts = SimpleNamespace(
        build_context=Mock(return_value="candidate and job context"),
        build_agent_orchestrator_prompt=Mock(return_value="agent prompt"),
    )
    agent = SimpleNamespace(system_prompt="Research agent")

    answer, sources = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question=(
            "Give me specific technology that highlight each candidate. "
            "Does it align with job requirements?"
        ),
        history=[],
    )

    assert "aligns with backend requirements" in answer
    assert sources == [{"document_id": 1}, {"document_id": 2}]
    rag.search_project_documents.assert_awaited_once()
    context_chunks = prompts.build_context.call_args.args[0]
    assert {chunk.document_name for chunk in context_chunks} == {
        "candidate_01_artem.txt",
        "job_description_senior_support_engineer.txt",
    }


@pytest.mark.asyncio
async def test_agent_retries_when_model_asks_user_to_do_delegated_work():
    ai = SimpleNamespace(
        generate_chat_response=AsyncMock(
            side_effect=[
                "candidate technology highlights\njob requirements",
                "Please provide details for each candidate.",
                "Candidate 01: Python and Django align with the job requirements.",
            ]
        )
    )
    rag = SimpleNamespace(
        search_project_documents=AsyncMock(return_value=[]),
        build_sources=Mock(return_value=[{"document_id": 1}]),
    )
    documents = SimpleNamespace(
        list_for_project=AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    filename="candidate_01_artem.txt",
                    text="Artem has Python and Django.",
                ),
            ]
        )
    )
    prompts = SimpleNamespace(
        build_context=Mock(return_value="candidate context"),
        build_agent_orchestrator_prompt=Mock(return_value="agent prompt"),
    )
    agent = SimpleNamespace(system_prompt="Research agent")

    answer, sources = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="Highlight each candidate's technology.",
        history=[],
    )

    assert "Candidate 01" in answer
    assert "Please provide" not in answer
    assert sources == [{"document_id": 1}]
    assert ai.generate_chat_response.await_count == 3


def _tool_call_result(name: str, arguments: dict, *, content: str | None = None):
    from app.services.ai.tool_types import ChatResult, ToolCall

    return ChatResult(content=content, tool_calls=[ToolCall(id="call_1", name=name, arguments=arguments)])


def _final_answer_result(content: str):
    from app.services.ai.tool_types import ChatResult

    return ChatResult(content=content, tool_calls=[])


@pytest.mark.asyncio
async def test_workspace_agent_calls_tool_and_returns_model_final_answer():
    # First turn: model calls a workspace tool. Second turn (after seeing the
    # tool result): model responds with plain text and no further tool call.
    ai = SimpleNamespace(
        generate_chat_response=AsyncMock(),
        generate_tool_call=AsyncMock(
            side_effect=[
                _tool_call_result("update_files_for_embedding_model", {}),
                _final_answer_result("Queued 1 document for re-embedding; 1 already current."),
            ]
        ),
    )
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        update_files_for_embedding_model=AsyncMock(
            return_value=ToolResult(
                tool="update_files_for_embedding_model",
                status="completed",
                data={"queued_rebuilds": [{"filename": "old.txt"}], "already_current": [{"filename": "current.txt"}]},
            )
        )
    )
    agent = SimpleNamespace(system_prompt="Workspace agent", workspace=True)

    answer, sources = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        workspace_tools=workspace_tools,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="Update files to fit the new embedding model.",
        history=[],
    )

    assert answer == "Queued 1 document for re-embedding; 1 already current."
    assert sources == []
    workspace_tools.update_files_for_embedding_model.assert_awaited_once()
    assert ai.generate_tool_call.await_count == 2
    ai.generate_chat_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_agent_retries_after_invalid_tool_arguments():
    # First turn: model calls create_workflow missing the required `name`
    # argument -- Pydantic validation fails and the error is reported back to
    # the model as a tool result. Second turn: model retries with valid
    # arguments. Third turn: model gives a final answer.
    ai = SimpleNamespace(
        generate_chat_response=AsyncMock(),
        generate_tool_call=AsyncMock(
            side_effect=[
                _tool_call_result("create_workflow", {}),
                _tool_call_result("create_workflow", {"name": "Extract invoice fields"}),
                _final_answer_result("Created the workflow `Extract invoice fields`."),
            ]
        ),
    )
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        create_workflow=AsyncMock(
            return_value=ToolResult(
                tool="create_workflow",
                status="completed",
                data={"id": 12, "name": "Extract invoice fields", "status": "pending"},
            )
        ),
    )
    agent = SimpleNamespace(system_prompt="Workspace agent", workspace=True)

    answer, _ = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        workspace_tools=workspace_tools,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="Create a workflow that extracts invoice fields.",
        history=[],
    )

    assert answer == "Created the workflow `Extract invoice fields`."
    workspace_tools.create_workflow.assert_awaited_once_with(
        workspace_tools.create_workflow.await_args.args[0],
        project_id=10,
        name="Extract invoice fields",
    )
    assert ai.generate_tool_call.await_count == 3
    ai.generate_chat_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_agent_falls_back_to_rag_when_model_calls_no_tool():
    # If the model never calls a workspace tool on the first turn, the
    # workspace router defers to the normal RAG/chat path instead of
    # returning anything itself.
    ai = SimpleNamespace(
        generate_chat_response=AsyncMock(return_value="General answer"),
        generate_tool_call=AsyncMock(return_value=_final_answer_result("not a workspace task")),
    )
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(
        build_context=Mock(return_value="context"),
        build_agent_orchestrator_prompt=Mock(return_value="prompt"),
    )
    workspace_tools = SimpleNamespace()
    agent = SimpleNamespace(system_prompt="Workspace agent", workspace=True)

    answer, _ = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        workspace_tools=workspace_tools,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="What's the capital of France?",
        history=[],
    )

    assert answer == "General answer"
    ai.generate_tool_call.assert_awaited_once()
    ai.generate_chat_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_lists_project_document_names_from_database():
    ai = SimpleNamespace(generate_chat_response=AsyncMock())
    rag = SimpleNamespace(
        search_project_documents=AsyncMock(),
        build_sources=Mock(return_value=[]),
    )
    documents = SimpleNamespace(
        list_for_project=AsyncMock(
            return_value=[
                SimpleNamespace(
                    filename="gmail_thread_large.txt",
                    status="indexed",
                    embedding_status="completed",
                ),
                SimpleNamespace(
                    filename="requirements_to_dev_tasks_mock_large.txt",
                    status="indexed",
                    embedding_status="completed",
                ),
            ]
        )
    )
    prompts = SimpleNamespace(
        build_context=Mock(return_value=""),
        build_agent_orchestrator_prompt=Mock(return_value="agent prompt"),
    )
    agent = SimpleNamespace(system_prompt="Project assistant")

    answer, sources = await AgentService(
        ai=ai,
        rag=rag,
        documents=documents,
        prompts=prompts,
    ).run(
        db=AsyncMock(),
        agent=agent,
        project_id=10,
        user_id=7,
        question="List all available document names.",
        history=[],
    )

    assert "`gmail_thread_large.txt`" in answer
    assert "`requirements_to_dev_tasks_mock_large.txt`" in answer
    assert sources == []
    documents.list_for_project.assert_awaited_once()
    rag.search_project_documents.assert_not_awaited()
    ai.generate_chat_response.assert_not_awaited()


def _agent_service_for_routing():
    return AgentService(
        ai=SimpleNamespace(),
        rag=SimpleNamespace(),
        documents=SimpleNamespace(),
        prompts=SimpleNamespace(),
    )


def test_needs_project_documents_ignores_assistant_mentions_of_documents():
    service = _agent_service_for_routing()
    history = [
        {"role": "user", "content": "hi there"},
        {
            "role": "assistant",
            "content": "I can help with project documents and files anytime.",
        },
    ]

    assert (
        service._needs_project_documents("what is the current llm provider?", history)
        is False
    )


def test_needs_project_documents_true_for_recent_user_document_mention():
    service = _agent_service_for_routing()
    history = [
        {"role": "user", "content": "can you summarize the uploaded contract?"},
        {"role": "assistant", "content": "Sure, here is a summary..."},
    ]

    assert (
        service._needs_project_documents("what does it say about renewal?", history)
        is True
    )


def test_needs_project_documents_false_beyond_recent_user_window():
    service = _agent_service_for_routing()
    history = [
        {"role": "user", "content": "can you summarize the uploaded contract?"},
        {"role": "assistant", "content": "Sure, here is a summary..."},
        {"role": "user", "content": "thanks"},
        {"role": "assistant", "content": "You're welcome."},
        {"role": "user", "content": "what is the current llm provider?"},
    ]

    assert (
        service._needs_project_documents("and the embedding provider?", history)
        is False
    )
