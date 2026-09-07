from typing import Optional, List
from pydantic import BaseModel, Field

class Task(BaseModel):
    task_id: int
    description: str       
    assigned_node: str     
    status: str = "pending" # pending, in_progress, completed, failed
    
    # Task ID dependencies for parallel scheduling (Ray DAG)
    depends_on: List[int] = Field(default_factory=list) 
    
    # Used for hierarchical tool routing, filled with major category (e.g., "WebScraping")
    required_category: Optional[str] = None 
    
    # Internal status record; after GenericAgent resolves categories, actual tool names can be stored here
    required_tools: List[str] = Field(default_factory=list) 
    
    role_prompt: str = ""

class Plan(BaseModel):
    tasks: List[Task] = Field(default_factory=list)

class PaperData(BaseModel):
    title: str
    url: str
    pdf_path: Optional[str] = None

class AgentState(BaseModel):
    user_topic: str
    search_source: str = "openalex"
    search_keywords_used: List[str] = Field(default_factory=list)
    
    memory_context: str = ""
    
    available_agents: str = ""
    available_tools: str = ""
    
    plan: Optional[Plan] = None
    search_report_content: Optional[str] = None
    search_report_file: Optional[str] = None
    top_paper: Optional[PaperData] = None
    final_translated_file: Optional[str] = None
    news_report: Optional[str] = None 
    
    chat_reply: Optional[str] = None
    
    current_phase: str = "init"
    is_aborted: bool = False

    # Scratchpad mechanism to store execution results of each step during multi-agent collaboration
    step_results: dict[int, str] = Field(default_factory=dict)
    execution_steps: List[dict] = Field(default_factory=list)
