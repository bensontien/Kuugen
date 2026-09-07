import json
import ray
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from factorys.agent_factory import AgentFactory
from core.registry import NodeRegistry
from core.orchestrator import KuugenOrchestrator
from core.memory import MemoryManager
from core.ray_manager import ToolManagerActor, RayToolManagerProxy

# ==========================================
# Define API Request and Response data structures
# ==========================================
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: Optional[str] = None
    news_report: Optional[str] = None
    search_report_file: Optional[str] = None
    translated_file: Optional[str] = None
    current_phase: str
    status: str = "success"

# ==========================================
# Prepare global variables
# ==========================================
kuugen_orchestrator = None
session_memories = {} 
tool_manager_actor = None
tool_manager_proxy = None

# ==========================================
# Define the unified Lifespan context manager
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global kuugen_orchestrator, tool_manager_actor, tool_manager_proxy
    llm_type = 'external' 
    
    # --- Startup Phase ---
    print("[Server] Initiating startup sequence...")

    # 0. Initialize Ray (Required for Parallel Orchestrator)
    if not ray.is_initialized():
        print("[Server] Initializing Ray Cluster...")
        # Optimization: disable dashboard and metrics to reduce errors
        ray.init(
            ignore_reinit_error=True,
            include_dashboard=False,
            _system_config={
                "metrics_report_interval_ms": -1,  # Disable metrics reporting
            },
            configure_logging=True,
            logging_level="warning"
        )
    
    # 1. Initialize ToolManager as a Ray Actor
    print("[Server] Starting ToolManagerActor...")
    tool_manager_actor = ToolManagerActor.remote(mcp_script_path="tools_server.py")
    await tool_manager_actor.initialize.remote()
    tool_manager_proxy = RayToolManagerProxy(tool_manager_actor)
            
    # 2. Initialize Factory and LLMs
    factory = AgentFactory() 
    orchestrator_llm = factory.get_llm(llm_type) 
    
    # 3. Inject dependencies into Agents
    search_agent = factory.get_agent('SearchPaperAgent', llm_type=llm_type)
    translator_agent = factory.get_agent('PDFTranslatorAgent', timeout=3600, llm_type='translator')
    news_agent = factory.get_agent('NewsAgent', llm_type=llm_type, tool_manager=tool_manager_proxy) 
    chat_agent = factory.get_agent('ChatAgent', llm_type=llm_type) 
    
    # 4. Create wrapper for standalone tools
    async def download_pdf_wrapper(state):
        url = state.top_paper.url 
        filename = state.top_paper.title
        result = await tool_manager_proxy.execute("download_pdf", url=url, filename=filename)
        state.chat_reply = result
        return state

    # 5. Build the Registry
    registry = NodeRegistry()
    registry.register("SearchPaperAgent", "Used for searching academic papers...", search_agent.run)
    registry.register("DownloadTool", "Used to attempt downloading PDF files.", download_pdf_wrapper)
    registry.register("TranslatorAgent", "Translate PDF files...", translator_agent.run)
    registry.register(
        "NewsAgent", 
        "Use ONLY when the user wants to SEARCH for general news, trends, or updates on a broad topic. DO NOT use this agent if the user provides a specific URL to read or scrape.", 
        news_agent.run
    )
    registry.register("ChatAgent", "General daily conversation...", chat_agent.run)
    
    # 6. Initialize the Orchestrator
    kuugen_orchestrator = KuugenOrchestrator(
        llm=orchestrator_llm, 
        registry=registry, 
        tool_manager=tool_manager_proxy,
        tool_manager_actor=tool_manager_actor
    )
    
    # --- Warm up Ray Actors ---
    print("[Server] Warming up parallel agents...")
    await kuugen_orchestrator.warm_up()
    
    print("[Server] Kuugen 2.0 API startup complete with Ray Parallel Support!")
    
    # --- Yield control back to FastAPI ---
    yield
    
    # --- Shutdown Phase ---
    print("[Server] Initiating shutdown sequence...")
    if tool_manager_actor:
        await tool_manager_actor.stop.remote()
    if ray.is_initialized():
        ray.shutdown()
    print("[Server] Shutdown complete.")

# ==========================================
# Create FastAPI instance
# ==========================================
app = FastAPI(title="Kuugen 2.0 API", version="1.0.0", lifespan=lifespan)

# Setup CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# WebSocket Endpoint
# ==========================================
@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    global kuugen_orchestrator, session_memories
    
    await websocket.accept()
    print("[WebSocket] Frontend connected!")
    
    def get_memory(session_id: str):
        if session_id not in session_memories:
            orchestrator_llm = AgentFactory().get_llm('external')
            session_memories[session_id] = MemoryManager(llm=orchestrator_llm, max_recent_turns=4)
        return session_memories[session_id]
    
    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            session_id = request_data.get("session_id", "default")
            user_message = request_data.get("message", "").strip()
            
            if not user_message:
                continue
                
            current_memory = get_memory(session_id)
            
            await websocket.send_json({
                "type": "status", 
                "content": "Thinking and planning (Ray Enabled)...",
                "session_id": session_id
            })
            
            current_memory.add_turn("User", user_message)
            context_str = await current_memory.get_context_and_compress()
            
            await websocket.send_json({
                "type": "status", 
                "content": "Executing parallel tasks via Ray...",
                "session_id": session_id
            })
            
            final_state = await kuugen_orchestrator.execute_task(user_message, memory_context=context_str)
            
            response_payload = {
                "type": "result",
                "reply": final_state.chat_reply,
                "news_report": final_state.news_report,
                "search_report_content": getattr(final_state, "search_report_content", None),
                "search_report_file": final_state.search_report_file,
                "translated_file": final_state.final_translated_file,
                "current_phase": final_state.current_phase,
                "session_id": session_id
            }
            await websocket.send_json(response_payload)
            
            assistant_reply_summary = []
            if final_state.chat_reply:
                assistant_reply_summary.append(final_state.chat_reply[:30] + "...")
            if final_state.news_report:
                assistant_reply_summary.append("Provided a news report.")
            if final_state.top_paper:
                assistant_reply_summary.append(f"Targeted paper: {final_state.top_paper.title}")
            current_memory.add_turn("Kuugen", " ".join(assistant_reply_summary))

    except WebSocketDisconnect:
        print("[WebSocket] Frontend disconnected.")
    except Exception as e:
        print(f"[WebSocket Error] {e}")
