import asyncio
import subprocess
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Callable, Awaitable

# ==========================================
# 1. Base Interface
# ==========================================
class Tool(ABC):
    def __init__(self, name: str, description: str, schema: Dict[str, Any], category: str = "general"):
        self.name = name
        self.description = description
        self.schema = schema
        self.category = category 

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Async execution interface for all tools."""
        pass

# ==========================================
# 2. Adapters
# ==========================================

class SkillTool(Tool):
    """Adapter for native Python function tools."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any], func: Callable[..., Awaitable[str]], category: str = "general"):
        super().__init__(name, description, schema, category)
        self.func = func

    async def execute(self, **kwargs) -> str:
        try:
            return await self.func(**kwargs)
        except Exception as e:
            return f"Error: Skill '{self.name}' execution failed: {e}"

class CLITool(Tool):
    """Adapter for command line tools with security interceptors."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any], is_windows: bool = False, category: str = "system_ops"):
        super().__init__(name, description, schema, category)
        self.is_windows = is_windows

    async def execute(self, command: str, **kwargs) -> str:
        cmd_lower = command.lower()
        
        # Security checks for Windows PowerShell
        if self.is_windows:
            dangerous_keywords = ['remove-item ', 'del ', 'rmdir ', 'stop-computer', 'restart-computer', 'stop-process', 'kill ']
            if any(k in cmd_lower for k in dangerous_keywords):
                return "System Protection: Potentially destructive command blocked."
            if 'format' in cmd_lower:
                safe_formats = ['format-table', 'format-list', 'format-wide', 'format-custom']
                if not any(s in cmd_lower for s in safe_formats):
                    return "System Protection: Disk formatting strictly prohibited."

        print(f"[CLITool] Executing command: {command}")
        
        def run_subprocess():
            # Platform specific execution
            shell_cmd = ["powershell.exe", "-Command", command] if self.is_windows else command
            return subprocess.run(
                shell_cmd, 
                shell=not self.is_windows, 
                capture_output=True, 
                text=True, 
                timeout=15
            )

        try:
            # Use asyncio.to_thread to avoid blocking FastAPI main thread
            result = await asyncio.to_thread(run_subprocess)
            if result.returncode == 0:
                output = result.stdout.strip()
                if len(output) > 3000:
                    output = output[:3000] + "\n...[Output Truncated]"
                return f"Success:\n{output}"
            else:
                return f"Error:\n{result.stderr.strip()}"
        except Exception as e:
            return f"CLI Error: {str(e)}"

class MCPTool(Tool):
    """Adapter for remote MCP server tool calls."""
    def __init__(self, name: str, description: str, schema: Dict[str, Any], mcp_client, category: str = "general"):
        super().__init__(name, description, schema, category)
        self.mcp_client = mcp_client

    async def execute(self, **kwargs) -> str:
        try:
            # Dispatch to MCP client
            return await self.mcp_client.execute_tool(self.name, **kwargs)
        except Exception as e:
            return f"Error: MCP Tool '{self.name}' execution failed: {e}"

# ==========================================
# 3. Tool Registry and Manager
# ==========================================
class ToolManager:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self.register_default_skills()

    def register_default_skills(self):
        """Register modular skills from .kuugen/skills/ as SkillTools."""
        import os
        from core.skill_manager import SkillManager

        async def _run_search_paper(topic: str = "", state: Any = None, llm: Any = None, **kwargs):
            from core.state import AgentState
            st = state or AgentState(user_topic=topic)
            if topic and not st.user_topic:
                st.user_topic = topic
            res_state = await SkillManager.execute_skill("search_paper", state=st, llm=llm, tool_manager=self, **kwargs)
            return res_state.search_report_content or res_state.chat_reply or "Paper search completed."

        async def _run_pdf_translator(pdf_path: str = "", state: Any = None, llm: Any = None, **kwargs):
            from core.state import AgentState, PaperData
            st = state or AgentState(user_topic="Translate")
            if pdf_path:
                st.top_paper = PaperData(title=os.path.basename(pdf_path), url="", pdf_path=pdf_path)
            res_state = await SkillManager.execute_skill("pdf_translator", state=st, llm=llm, tool_manager=self, **kwargs)
            return f"Translation completed: {res_state.final_translated_file}" if res_state.final_translated_file else "Translation completed."

        async def _run_news_search(topic: str = "", state: Any = None, llm: Any = None, **kwargs):
            from core.state import AgentState
            st = state or AgentState(user_topic=topic)
            if topic and not st.user_topic:
                st.user_topic = topic
            res_state = await SkillManager.execute_skill("news_search", state=st, llm=llm, tool_manager=self, **kwargs)
            return res_state.news_report or "News search completed."

        self.register_tool(SkillTool(
            name="search_paper",
            description="Deep academic paper search across ArXiv and OpenAlex top journals, 6-dimension scoring, snowballing, and review report generation.",
            schema={
                "properties": {"topic": {"type": "string", "description": "Academic research topic or query string"}},
                "required": ["topic"]
            },
            func=_run_search_paper,
            category="academic_research"
        ))
        self.register_tool(SkillTool(
            name="pdf_translator",
            description="Translate an academic PDF paper into Traditional Chinese markdown with formula preservation.",
            schema={
                "properties": {"pdf_path": {"type": "string", "description": "Local file path to the PDF paper"}},
                "required": ["pdf_path"]
            },
            func=_run_pdf_translator,
            category="academic_translation"
        ))
        self.register_tool(SkillTool(
            name="news_search",
            description="Search real-time bilingual news, scrape webpages, and synthesize trends.",
            schema={
                "properties": {"topic": {"type": "string", "description": "News topic to search for"}},
                "required": ["topic"]
            },
            func=_run_news_search,
            category="web_scraping"
        ))

    def register_tool(self, tool: Tool):
        """Register a new tool."""
        self._tools[tool.name] = tool
        print(f"[ToolManager] Registered {tool.__class__.__name__}: {tool.name} (Category: {tool.category})")

    def get_skill_catalog(self) -> str:
        """Returns a concise catalog of registered tool categories for the Orchestrator."""
        categories = set(t.category for t in self._tools.values())
        if not categories:
            return "No skill categories available."
            
        catalog_items = []
        for cat in categories:
            catalog_items.append(f"- **{cat}**: Tools related to {cat.replace('_', ' ')}.")
            
        return "\n".join(catalog_items)

    def get_schemas_by_category(self, category: str) -> str:
        """Returns detailed tool schemas for a specific category."""
        matched_tools = [t for t in self._tools.values() if t.category == category]
        if not matched_tools:
            return "No tools found for this category."
            
        schemas = [
            json.dumps({
                "name": t.name, 
                "description": t.description, 
                "schema": t.schema
            }, ensure_ascii=False) 
            for t in matched_tools
        ]
        return "\n".join(schemas)

    def get_all_schemas(self) -> str:
        """Returns unified tool schema documentation."""
        schemas = [
            json.dumps({
                "name": t.name, 
                "description": t.description, 
                "schema": t.schema
            }, ensure_ascii=False) 
            for t in self._tools.values()
        ]
        return "\n".join(schemas)

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_all_tool_descriptions(self) -> str:
        """Returns a list of all tools and their descriptions."""
        if not self._tools:
            return "No tools registered."
        return "\n".join([f"- {t.name}: {t.description}" for t in self._tools.values()])

    async def execute(self, tool_name: str, **kwargs) -> str:
        """Unified entry point for tool execution."""
        if tool_name not in self._tools:
            return f"Error: Tool '{tool_name}' not found."
        
        tool_instance = self._tools[tool_name]
        print(f"\n[ToolManager] Dispatching to {tool_instance.__class__.__name__}: {tool_name}")
        return await tool_instance.execute(**kwargs)