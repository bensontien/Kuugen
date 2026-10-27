import pytest
from core.base_agent import BaseAgent
from core.state import AgentState

@pytest.mark.asyncio
async def test_base_agent_interface():
    agent = BaseAgent(llm=None, tool_manager=None, timeout=60.0, verbose=True)
    assert agent.timeout == 60.0
    assert agent.verbose is True

    state = AgentState(user_topic="test")
    with pytest.raises(NotImplementedError):
        await agent.run(state)

@pytest.mark.asyncio
async def test_concrete_agent_subclass():
    class DummyAgent(BaseAgent):
        async def run(self, state: AgentState) -> AgentState:
            state.chat_reply = f"Processed: {state.user_topic}"
            return state

    agent = DummyAgent()
    state = AgentState(user_topic="Kuugen Test")
    result = await agent.run(state)
    assert result.chat_reply == "Processed: Kuugen Test"
