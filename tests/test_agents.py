import pytest
from unittest.mock import AsyncMock, MagicMock
from core.state import AgentState
from core.llm_client import LLMResponse
from agents.generic_agent import GenericAgent

class MockLLM:
    def __init__(self, reply_text="Mock Response"):
        self.reply_text = reply_text

    async def acomplete(self, prompt: str, **kwargs):
        return LLMResponse(text=self.reply_text)

class FailingLLM:
    async def acomplete(self, prompt: str, **kwargs):
        raise RuntimeError("LLM connection timeout")

@pytest.mark.asyncio
async def test_react_direct_answer_chat_mode():
    """Verifies that GenericAgent functions as a conversational agent when no tools are needed."""
    llm = MockLLM("Hello! I am Kuugen, your AI assistant.")
    agent = GenericAgent(llm=llm, task_id=1, system_prompt="You are a helpful assistant.")
    state = AgentState(user_topic="Hi, who are you?")
    
    result = await agent.run(state)
    assert result.chat_reply == "Hello! I am Kuugen, your AI assistant."
    assert result.step_results[1] == "Hello! I am Kuugen, your AI assistant."
    assert not result.is_aborted

@pytest.mark.asyncio
async def test_react_single_tool_execution():
    """Verifies Think -> Action -> Observation -> Final Answer sequence."""
    tool_action = '```json\n{"action": "test_calculator", "arguments": {"expr": "40 + 2"}}\n```'
    final_answer = "The calculated answer is 42."

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text=tool_action),
        LLMResponse(text=final_answer)
    ])

    mock_tool_manager = MagicMock()
    mock_tool_manager.get_schemas_by_category = MagicMock(return_value="test tool schema")
    mock_tool_manager.execute = AsyncMock(return_value="42")

    agent = GenericAgent(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        required_category="general",
        task_id=1
    )
    state = AgentState(user_topic="Calculate 40 + 2")
    result = await agent.run(state)

    mock_tool_manager.execute.assert_awaited_once_with("test_calculator", state=state, llm=mock_llm, expr="40 + 2")
    assert result.chat_reply == final_answer
    assert result.step_results[1] == final_answer

@pytest.mark.asyncio
async def test_react_multi_step_tool_chaining():
    """Verifies multi-step tool execution chaining across iterations."""
    step1_action = '```json\n{"action": "step1_tool", "arguments": {"query": "init"}}\n```'
    step2_action = '```json\n{"action": "step2_tool", "arguments": {"data": "step1_output"}}\n```'
    final_answer = "Completed multi-step workflow successfully."

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text=step1_action),
        LLMResponse(text=step2_action),
        LLMResponse(text=final_answer)
    ])

    mock_tool_manager = MagicMock()
    mock_tool_manager.get_schemas_by_category = MagicMock(return_value="schemas")
    mock_tool_manager.execute = AsyncMock(side_effect=[
        "step1_output",
        "step2_output"
    ])

    agent = GenericAgent(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        required_category="general",
        task_id=2,
        max_steps=5
    )
    state = AgentState(user_topic="Run two tools in sequence")
    result = await agent.run(state)

    assert mock_tool_manager.execute.await_count == 2
    assert result.chat_reply == final_answer

@pytest.mark.asyncio
async def test_react_skill_dispatch():
    """Verifies that GenericAgent detects and dispatches skill calls directly to SkillManager."""
    from unittest.mock import patch
    skill_action = '```json\n{"action": "news_search", "arguments": {"topic": "AI"}}\n```'
    final_answer = "Here is the summary of news on AI."

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text=skill_action),
        LLMResponse(text=final_answer)
    ])

    with patch("core.skill_manager.SkillManager.execute_skill", new_callable=AsyncMock) as mock_exec:
        dummy_state = AgentState(user_topic="AI")
        dummy_state.news_report = "Mocked news report content"
        mock_exec.return_value = dummy_state

        agent = GenericAgent(
            llm=mock_llm,
            tool_manager=MagicMock(),
            required_category="web_scraping",
            task_id=3
        )
        state = AgentState(user_topic="Search news on AI")
        result = await agent.run(state)

        mock_exec.assert_awaited_once()
        assert result.chat_reply == final_answer

@pytest.mark.asyncio
async def test_react_max_steps_guard():
    """Verifies that ReAct loop halts and consolidates when reaching max_steps limit."""
    infinite_tool_action = '```json\n{"action": "test_loop", "arguments": {}}\n```'

    mock_llm = MagicMock()
    # Return tool action on all turns plus final consolidation summary
    mock_llm.acomplete = AsyncMock(side_effect=[
        LLMResponse(text=infinite_tool_action),
        LLMResponse(text=infinite_tool_action),
        LLMResponse(text=infinite_tool_action),
        LLMResponse(text="Forced consolidation summary after reaching limit.")
    ])

    mock_tool_manager = MagicMock()
    mock_tool_manager.get_schemas_by_category = MagicMock(return_value="schemas")
    mock_tool_manager.execute = AsyncMock(return_value="tool output")

    agent = GenericAgent(
        llm=mock_llm,
        tool_manager=mock_tool_manager,
        task_id=4,
        max_steps=3 # Low step limit for test
    )
    state = AgentState(user_topic="Infinite loop test")
    result = await agent.run(state)

    assert mock_tool_manager.execute.await_count == 3
    assert result.chat_reply == "Forced consolidation summary after reaching limit."

@pytest.mark.asyncio
async def test_react_llm_error_handling():
    """Verifies graceful error handling when LLM fails during execution."""
    agent = GenericAgent(llm=FailingLLM(), task_id=5)
    state = AgentState(user_topic="Test failing LLM")
    result = await agent.run(state)

    assert "Error during reasoning" in result.chat_reply
