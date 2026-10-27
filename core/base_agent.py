from typing import Optional, Any
from core.state import AgentState

class BaseAgent:
    """
    Native base class for all Kuugen Agents.
    Replaces LlamaIndex Workflow with pure asyncio execution.
    """
    def __init__(
        self,
        llm: Any = None,
        tool_manager: Any = None,
        timeout: float = 3600.0,
        verbose: bool = False,
        **kwargs
    ):
        self.llm = llm
        self.tool_manager = tool_manager
        self.timeout = timeout
        self.verbose = verbose
        self.extra_kwargs = kwargs

    async def run(self, state: AgentState) -> AgentState:
        """
        Execute the agent logic given the current AgentState and return the updated AgentState.
        Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement run(state: AgentState)")
