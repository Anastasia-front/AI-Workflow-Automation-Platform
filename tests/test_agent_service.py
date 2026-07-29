from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.enums import DocumentStatus
from app.services.agent import AgentService


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


@pytest.mark.asyncio
async def test_workspace_agent_updates_files_via_workspace_tools():
    ai = SimpleNamespace(generate_chat_response=AsyncMock())
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        update_files_for_embedding_model=AsyncMock(
            return_value=SimpleNamespace(
                data={
                    "embedding_config": {
                        "provider": "gemini",
                        "model": "text-embedding-004",
                        "dimensions": 768,
                    },
                    "queued_rebuilds": [{"filename": "old.txt"}],
                    "already_current": [{"filename": "current.txt"}],
                    "active_jobs": [],
                    "not_ready": [],
                    "failed": [],
                }
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

    assert "Queued rebuilds: 1" in answer
    assert "`old.txt`" in answer
    assert "`current.txt`" in answer
    assert sources == []
    workspace_tools.update_files_for_embedding_model.assert_awaited_once()
    ai.generate_chat_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_agent_creates_invoice_workflow_with_real_extraction_steps():
    ai = SimpleNamespace(generate_chat_response=AsyncMock())
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(list_for_project=AsyncMock(return_value=[]))
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        create_workflow=AsyncMock(
            return_value=SimpleNamespace(data={"id": 12, "name": "Extract invoice fields", "status": "pending"})
        ),
        create_workflow_step=AsyncMock(
            side_effect=[
                SimpleNamespace(data={"id": 37, "name": "Extract invoice fields", "step_order": 1}),
                SimpleNamespace(data={"id": 38, "name": "Validate invoice fields", "step_order": 2}),
            ]
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

    assert "Extract invoice fields" in answer
    assert workspace_tools.create_workflow_step.await_count == 2
    first_step = workspace_tools.create_workflow_step.await_args_list[0].kwargs
    second_step = workspace_tools.create_workflow_step.await_args_list[1].kwargs
    assert "Do not describe a workflow" in first_step["prompt_template"]
    assert "{{input}}" in first_step["prompt_template"]
    assert second_step["depends_on"] == [37]
    ai.generate_chat_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_agent_requires_document_when_workflow_input_is_ambiguous():
    ai = SimpleNamespace(generate_chat_response=AsyncMock())
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(
        list_for_project=AsyncMock(
            return_value=[
                SimpleNamespace(id=1, filename="invoice_january.txt", status=DocumentStatus.INDEXED, text="Invoice January"),
                SimpleNamespace(id=2, filename="invoice_february.txt", status=DocumentStatus.INDEXED, text="Invoice February"),
            ]
        )
    )
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        list_workflows=AsyncMock(
            return_value=SimpleNamespace(data={"workflows": [{"id": 12, "name": "Extract invoice fields", "status": "pending"}]})
        ),
        run_workflow=AsyncMock(),
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
        question="Run workflow Extract invoice fields.",
        history=[],
    )

    assert "Which document" in answer
    workspace_tools.run_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_workspace_agent_runs_workflow_with_selected_document_text():
    ai = SimpleNamespace(generate_chat_response=AsyncMock())
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(
        list_for_project=AsyncMock(
            return_value=[
                SimpleNamespace(id=1, filename="invoice_january.txt", status=DocumentStatus.INDEXED, text="Invoice Number: INV-1"),
                SimpleNamespace(id=2, filename="notes.txt", status=DocumentStatus.INDEXED, text="Notes"),
            ]
        )
    )
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        list_workflows=AsyncMock(
            return_value=SimpleNamespace(data={"workflows": [{"id": 12, "name": "Extract invoice fields", "status": "pending"}]})
        ),
        run_workflow=AsyncMock(
            return_value=SimpleNamespace(data={"run_id": 18, "workflow_id": 12, "task_id": "task-1", "status": "pending"})
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
        question="Run workflow Extract invoice fields on invoice_january.txt.",
        history=[],
    )

    assert "invoice_january.txt" in answer
    kwargs = workspace_tools.run_workflow.await_args.kwargs
    assert kwargs["workflow_id"] == 12
    assert "Document filename: invoice_january.txt" in kwargs["user_input"]
    assert "Invoice Number: INV-1" in kwargs["user_input"]


@pytest.mark.asyncio
async def test_workspace_agent_runs_workflow_with_natural_phrasing():
    # Regression test: "run the workflow ..." (not the literal substring
    # "run workflow") used to fall through to a plain chat answer instead
    # of actually executing the workflow.
    ai = SimpleNamespace(generate_chat_response=AsyncMock())
    rag = SimpleNamespace(search_project_documents=AsyncMock(), build_sources=Mock(return_value=[]))
    documents = SimpleNamespace(
        list_for_project=AsyncMock(
            return_value=[
                SimpleNamespace(id=1, filename="meeting_minutes_mock_large.txt", status=DocumentStatus.INDEXED, text="Meeting notes"),
            ]
        )
    )
    prompts = SimpleNamespace(build_context=Mock(), build_agent_orchestrator_prompt=Mock())
    workspace_tools = SimpleNamespace(
        list_workflows=AsyncMock(
            return_value=SimpleNamespace(
                data={"workflows": [{"id": 111, "name": "Workspace generated workflow", "status": "pending"}]}
            )
        ),
        run_workflow=AsyncMock(
            return_value=SimpleNamespace(data={"run_id": 97, "workflow_id": 111, "task_id": "task-2", "status": "pending"})
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
        question=(
            "run the workflow which has only 2 steps (analyzed input and "
            "analyze output) and use meeting_minutes_mock_large.txt file for it"
        ),
        history=[],
    )

    assert "meeting_minutes_mock_large.txt" in answer
    workspace_tools.run_workflow.assert_awaited_once()
    ai.generate_chat_response.assert_not_awaited()


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
