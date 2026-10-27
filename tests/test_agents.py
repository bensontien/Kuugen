import pytest
import os
from unittest.mock import AsyncMock, MagicMock
from core.state import AgentState, PaperData
from core.llm_client import LLMResponse
from agents.chat_agent import ChatAgent
from agents.generic_agent import GenericAgent
from agents.news_agent import NewsAgent
from agents.translator_agent import PDFTranslatorAgent
from agents.searchpaper_agent import SearchPaperAgent

class MockLLM:
    def __init__(self, reply_text="Mock Response"):
        self.reply_text = reply_text

    async def acomplete(self, prompt: str, **kwargs):
        return LLMResponse(text=self.reply_text)

class FailingLLM:
    async def acomplete(self, prompt: str, **kwargs):
        raise RuntimeError("LLM connection timeout")

@pytest.mark.asyncio
async def test_chat_agent_success():
    llm = MockLLM("Hello! I am Kuugen.")
    agent = ChatAgent(llm=llm)
    state = AgentState(user_topic="Hi")
    result = await agent.run(state)
    assert result.chat_reply == "Hello! I am Kuugen."
    assert not result.is_aborted

@pytest.mark.asyncio
async def test_chat_agent_error():
    llm = FailingLLM()
    agent = ChatAgent(llm=llm)
    state = AgentState(user_topic="Hi")
    result = await agent.run(state)
    assert result.chat_reply == "ERROR"

@pytest.mark.asyncio
async def test_generic_agent_direct_answer():
    llm = MockLLM("Here is direct explanation without tools.")
    agent = GenericAgent(llm=llm, task_id=1, system_prompt="You are helper.")
    state = AgentState(user_topic="Explain quantum computing")
    result = await agent.run(state)
    assert result.chat_reply == "Here is direct explanation without tools."
    assert result.step_results[1] == "Here is direct explanation without tools."

@pytest.mark.asyncio
async def test_generic_agent_tool_calling():
    # First response returns JSON tool action, second summary response returns final text
    tool_json = '```json\n{"action": "test_tool", "arguments": {"query": "test"}}\n```'
    summary_text = "Tool execution was successful and summarized."
    
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text=tool_json),
        LLMResponse(text=summary_text)
    ])
    
    mock_tool_manager = MagicMock()
    mock_tool_manager.execute = AsyncMock(return_value="Raw tool execution output")
    mock_tool_manager.get_schemas_by_category = MagicMock(return_value="tool schema")

    agent = GenericAgent(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        required_category="general",
        task_id=2
    )
    state = AgentState(user_topic="Run tool")
    result = await agent.run(state)

    mock_tool_manager.execute.assert_awaited_once_with("test_tool", query="test")
    assert result.chat_reply == summary_text
    assert result.step_results[2] == summary_text

@pytest.mark.asyncio
async def test_news_agent_fallback_on_empty():
    llm = MockLLM("News Summary")
    mock_tool_manager = MagicMock()
    agent = NewsAgent(llm=llm, tool_manager=mock_tool_manager)
    # Give an empty topic so search returns empty or handled safely
    state = AgentState(user_topic="")
    result = await agent.run(state)
    assert result.news_report is not None

@pytest.mark.asyncio
async def test_translator_agent_no_paper():
    agent = PDFTranslatorAgent(llm=MockLLM())
    state = AgentState(user_topic="Translate")
    result = await agent.run(state)
    assert result.is_aborted is True

@pytest.mark.asyncio
async def test_translator_agent_missing_file():
    agent = PDFTranslatorAgent(llm=MockLLM())
    state = AgentState(user_topic="Translate")
    state.top_paper = PaperData(title="NonExistent", url="http://example.com", pdf_path="/tmp/nonexistent_paper_12345.pdf")
    result = await agent.run(state)
    assert result.is_aborted is True

@pytest.mark.asyncio
async def test_searchpaper_agent_pipeline():
    scoring_response = "Evaluation result:\nTotal Score: 52\nHigh technical depth."
    summary_response = "這是一篇關於多代理人架構的文獻。"

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text=scoring_response),
        LLMResponse(text=summary_response)
    ])

    agent = SearchPaperAgent(llm=mock_llm)
    state = AgentState(user_topic="Multi-Agent Systems")

    dummy_papers = [
        {
            "title": "Decoupled Multi-Agent Systems",
            "summary": "This abstract presents a comprehensive study of decoupled multi-agent architectures with high rigor and extensive evaluation.",
            "url": "http://arxiv.org/abs/1234.5678",
            "venue": "IEEE TPAMI",
            "date": "2026-03-01",
            "id": "1234.5678"
        }
    ]

    # Test scoring
    state, scored = await agent.score_papers(state, dummy_papers)
    assert len(scored) == 1
    assert scored[0]["score"] == 52

    # Test summary
    state, scored, report = await agent.generate_summary(state, scored)
    assert "Decoupled Multi-Agent Systems" in report
    assert "52/60" in report

    # Test saving report
    state = await agent.save_report(state, scored, report)
    assert state.search_report_file is not None
    assert os.path.exists(state.search_report_file)
    assert state.top_paper.title == "Decoupled Multi-Agent Systems"
    assert state.chat_reply == "Search completed and report generated."
