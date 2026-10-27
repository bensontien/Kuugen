import pytest
from core.state import AgentState
from core.skill_manager import SkillManager
from core.llm_client import LLMResponse
from unittest.mock import MagicMock, AsyncMock

def test_list_available_skills():
    skills = SkillManager.list_available_skills()
    assert "search_paper" in skills
    assert "pdf_translator" in skills
    assert "news_search" in skills
    assert skills["search_paper"]["name"] == "search_paper"
    assert "search" in skills["search_paper"]["description"].lower()
    assert "translation" in skills["pdf_translator"]["description"].lower()
    assert "news" in skills["news_search"]["description"].lower()

@pytest.mark.asyncio
async def test_execute_search_paper_skill():
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text="Evaluation result:\nTotal Score: 50"),
        LLMResponse(text="總結內容")
    ])

    state = AgentState(user_topic="Machine Learning")
    dummy_papers = [
        {
            "title": "Deep Learning Survey",
            "summary": "This is a detailed summary exceeding fifty characters length for testing scoring functionality properly.",
            "url": "http://arxiv.org/abs/5678.9999",
            "venue": "Nature Machine Intelligence",
            "date": "2026-01-01",
            "id": "5678.9999"
        }
    ]

    skill_module = SkillManager.load_skill_module("search_paper")
    state, scored = await skill_module.score_papers(state, dummy_papers, mock_llm)
    assert len(scored) == 1
    assert scored[0]["score"] == 50

@pytest.mark.asyncio
async def test_execute_pdf_translator_skill():
    state = AgentState(user_topic="Translate Paper")
    result = await SkillManager.execute_skill("pdf_translator", state=state, llm=MagicMock())
    assert result.is_aborted is True

@pytest.mark.asyncio
async def test_execute_news_search_skill():
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value=LLMResponse(text="News Summary Report"))

    state = AgentState(user_topic="")
    result = await SkillManager.execute_skill("news_search", state=state, llm=mock_llm, tool_manager=None)
    assert result.news_report == "News Summary Report"
