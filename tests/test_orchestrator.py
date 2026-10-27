import pytest
import json
from core.state import AgentState, Plan, Task
from core.registry import NodeRegistry
from core.orchestrator import KuugenOrchestrator
from core.llm_client import LLMResponse

class MockPlanLLM:
    def __init__(self, plan_data=None):
        self.plan_data = plan_data or {
            "tasks": [
                {
                    "task_id": 1,
                    "description": "Chat with user",
                    "assigned_node": "ChatAgent",
                    "depends_on": []
                }
            ]
        }

    async def acomplete(self, prompt: str, **kwargs):
        return LLMResponse(text=f"```json\n{json.dumps(self.plan_data)}\n```")

@pytest.mark.asyncio
async def test_orchestrator_planning():
    registry = NodeRegistry()
    registry.register("ChatAgent", "Chat agent description", lambda state: state)
    
    mock_llm = MockPlanLLM()
    orchestrator = KuugenOrchestrator(llm=mock_llm, registry=registry)
    
    plan = await orchestrator._generate_plan("Hello Kuugen")
    assert len(plan.tasks) == 1
    assert plan.tasks[0].task_id == 1
    assert plan.tasks[0].assigned_node == "ChatAgent"

@pytest.mark.asyncio
async def test_orchestrator_local_execution():
    registry = NodeRegistry()
    
    async def mock_chat_node(state: AgentState):
        state.chat_reply = "Response from mock chat node"
        return state

    registry.register("ChatAgent", "Chat agent description", mock_chat_node)
    
    mock_llm = MockPlanLLM()
    orchestrator = KuugenOrchestrator(llm=mock_llm, registry=registry)
    
    final_state = await orchestrator.execute_task("Hello")
    assert final_state.chat_reply == "Response from mock chat node"
    assert final_state.current_phase == "finished"
