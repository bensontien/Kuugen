import ray
import inspect
import asyncio
from typing import Dict, Any, List, Optional
from core.state import AgentState, Task

@ray.remote(num_cpus=0)
class ToolManagerActor:
    """
    Centralized tool management Actor.
    Initializes MCP client and tools internally to resolve serialization issues.
    """
    def __init__(self, mcp_script_path: str = "tools_server.py"):
        from core.tool_manager import ToolManager
        from core.mcp_client import KuugenMCPClient
        self.tool_manager = ToolManager()
        self.mcp_client = KuugenMCPClient(server_script_path=mcp_script_path)

    async def initialize(self):
        """Async initialization for MCP client and tool registration"""
        from core.tool_manager import CLITool, MCPTool
        print("[ToolManagerActor] Starting MCP Client...")
        await self.mcp_client.start()
        
        self.tool_manager.register_tool(CLITool(
            name="execute_windows_command",
            description="Execute a command in the host Windows PowerShell from WSL. Use this to check system status, open apps, or read files.",
            schema={
                "properties": {"command": {"type": "string", "description": "PowerShell command to execute"}},
                "required": ["command"]
            },
            is_windows=True,
            category="system_ops"
        ))
        
        if self.mcp_client.session:
            mcp_tools = await self.mcp_client.session.list_tools() 
            for t in mcp_tools.tools:
                cat = "web_scraping" if "fetch" in t.name or "scrape" in t.name else "general"
                self.tool_manager.register_tool(MCPTool(
                    name=t.name,
                    description=t.description,
                    schema=t.inputSchema,
                    mcp_client=self.mcp_client,
                    category=cat
                ))
        print("[ToolManagerActor] Tools initialized successfully.")
        return True

    async def execute(self, tool_name: str, **kwargs):
        print(f"[ToolManagerActor] Executing tool: {tool_name}")
        return await self.tool_manager.execute(tool_name, **kwargs)

    def get_schemas_by_category(self, category: str):
        return self.tool_manager.get_schemas_by_category(category)

    def get_all_schemas(self):
        return self.tool_manager.get_all_schemas()

    def get_all_tool_descriptions(self):
        return self.tool_manager.get_all_tool_descriptions()
        
    async def stop(self):
        print("[ToolManagerActor] Stopping MCP Client...")
        await self.mcp_client.stop()

@ray.remote(num_cpus=0)
class FunctionActor:
    """
    A lightweight Actor wrapper for plain callable functions.
    Used for nodes that are not full Agents and can be safely pickled.
    """
    def __init__(self, name: str, func: Any):
        self.name = name
        self.func = func
        
    async def initialize(self):
        """Dummy initialization for parallel compatibility."""
        return True
        
    async def run(self, state: AgentState) -> AgentState:
        print(f"[Ray Actor: {self.name}] Executing function wrapper...")
        try:
            result = self.func(state)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            print(f"[Ray Actor: {self.name}] Error: {e}")
            state.is_aborted = True
            return state

@ray.remote(num_cpus=0)
class AgentActor:
    def __init__(self, agent_type: str, llm_type: str = 'external', tool_manager_actor=None):
        self.agent_type = agent_type
        self.llm_type = llm_type
        self.agent = None
        self._factory = None
        self.tool_manager_actor = tool_manager_actor # Reference to ToolManager Actor

    async def initialize(self):
        """Eagerly initialize the Agent instance."""
        if self.agent is None:
            print(f"[Ray Actor: {self.agent_type}] Initializing Agent instance...")
            if self._factory is None:
                from factorys.agent_factory import AgentFactory
                self._factory = AgentFactory()
            
            # Inject a Proxy that can call the Ray Actor if the Agent needs tools
            self.agent = self._factory.get_agent(
                self.agent_type, 
                llm_type=self.llm_type,
                tool_manager=RayToolManagerProxy(self.tool_manager_actor) if self.tool_manager_actor else None
            )
        return True

    async def run(self, state: AgentState) -> AgentState:
        if self.agent is None:
            await self.initialize()
        
        print(f"[Ray Actor: {self.agent_type}] Executing task...")
        try:
            result = self.agent.run(state=state)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            print(f"[Ray Actor: {self.agent_type}] Error: {e}")
            import traceback
            traceback.print_exc()
            state.is_aborted = True
            return state

@ray.remote(num_cpus=0)
class GenericAgentActor:
    def __init__(self, llm_type: str = 'external', tool_manager_actor=None):
        self.llm_type = llm_type
        self.tool_manager_actor = tool_manager_actor
        self._factory = None

    async def initialize(self):
        """Dummy initialization for parallel compatibility."""
        return True

    async def run(self, state: AgentState, task_dict: dict) -> AgentState:
        from agents.generic_agent import GenericAgent
        if self._factory is None:
            self._factory = AgentFactory()
        
        llm = self._factory.get_llm(self.llm_type)
        task = Task(**task_dict)
        
        print(f"[Ray Actor: GenericAgent] Executing step {task.task_id}")
        
        agent = GenericAgent(
            llm=llm,
            tool_manager=RayToolManagerProxy(self.tool_manager_actor) if self.tool_manager_actor else None,
            required_category=task.required_category,
            system_prompt=task.role_prompt if task.role_prompt else "Use tools to help user.",
            task_id=task.task_id
        )
        return await agent.run(state=state)

class RayToolManagerProxy:
    """
    Lightweight proxy that mimics ToolManager but executes tools remotely via Ray Actor.
    """
    def __init__(self, actor_handle):
        self.actor_handle = actor_handle

    async def execute(self, tool_name: str, **kwargs):
        # Remote execution via Ray Actor
        return await self.actor_handle.execute.remote(tool_name, **kwargs)

    def get_schemas_by_category(self, category: str):
        return ray.get(self.actor_handle.get_schemas_by_category.remote(category))

    def get_all_schemas(self):
        return ray.get(self.actor_handle.get_all_schemas.remote())

    def get_all_tool_descriptions(self):
        return ray.get(self.actor_handle.get_all_tool_descriptions.remote())

def merge_states(base_state: AgentState, *new_states: AgentState) -> AgentState:
    for s in new_states:
        if not s: continue
        base_state.step_results.update(s.step_results)
        if s.chat_reply: base_state.chat_reply = s.chat_reply
        if s.news_report: base_state.news_report = s.news_report
        if s.search_report_content: base_state.search_report_content = s.search_report_content
        if s.search_report_file: base_state.search_report_file = s.search_report_file
        if s.top_paper: base_state.top_paper = s.top_paper
        if s.final_translated_file: base_state.final_translated_file = s.final_translated_file
        if s.is_aborted: base_state.is_aborted = True
    return base_state
