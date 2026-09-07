import json
import asyncio
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
    import time
    t_start = time.perf_counter()
    print("[Server] Initiating Kuugen 2.0 startup sequence...")

    # 0. Initialize Ray (Required for Parallel Orchestrator)
    if not ray.is_initialized():
        print("[Server] Initializing Ray Cluster...")
        ray.init(
            ignore_reinit_error=True,
            include_dashboard=False,
            _system_config={
                "metrics_report_interval_ms": -1,  # Disable metrics reporting
            },
            configure_logging=True,
            logging_level="warning"
        )
    
    # 1. Initialize ToolManager as a Ray Actor (FIFO mailbox guarantees initialize runs before any tool request)
    print("[Server] Starting ToolManagerActor...")
    tool_manager_actor = ToolManagerActor.remote(mcp_script_path="tools_server.py")
    tool_manager_actor.initialize.remote()
    tool_manager_proxy = RayToolManagerProxy(tool_manager_actor)
            
    # 2. Initialize Factory and Registry
    factory = AgentFactory() 
    
    # 3. Create wrapper for standalone tools
    async def download_pdf_wrapper(state):
        url = state.top_paper.url 
        filename = state.top_paper.title
        result = await tool_manager_proxy.execute("download_pdf", url=url, filename=filename)
        state.chat_reply = result
        return state

    # 4. Build the Registry (Lazy runners for fallback mode, avoids importing unused agents in main process)
    registry = NodeRegistry()
    registry.register("SearchPaperAgent", "Used for searching academic papers...", lambda state: factory.get_agent('SearchPaperAgent', llm_type=llm_type).run(state))
    registry.register("DownloadTool", "Used to attempt downloading PDF files.", download_pdf_wrapper)
    registry.register("TranslatorAgent", "Translate PDF files...", lambda state: factory.get_agent('PDFTranslatorAgent', timeout=3600, llm_type='translator').run(state))
    registry.register(
        "NewsAgent", 
        "Use ONLY when the user wants to SEARCH for general news, trends, or updates on a broad topic. DO NOT use this agent if the user provides a specific URL to read or scrape.", 
        lambda state: factory.get_agent('NewsAgent', llm_type=llm_type, tool_manager=tool_manager_proxy).run(state)
    )
    registry.register("ChatAgent", "General daily conversation...", lambda state: factory.get_agent('ChatAgent', llm_type=llm_type).run(state))
    
    # 5. Initialize the Orchestrator with lazy LLM resolver
    kuugen_orchestrator = KuugenOrchestrator(
        llm=lambda: factory.get_llm(llm_type), 
        registry=registry, 
        tool_manager=tool_manager_proxy,
        tool_manager_actor=tool_manager_actor
    )
    
    # --- Warm up Ray Actors (Non-blocking background task) ---
    print("[Server] Starting parallel agents warm-up in background...")
    asyncio.create_task(kuugen_orchestrator.warm_up())
    
    print(f"[Server] Kuugen 2.0 API startup complete in {time.perf_counter() - t_start:.2f}s with Ray Parallel Support!")
    
    # --- Yield control back to FastAPI ---
    yield
    
    # --- Shutdown Phase ---
    print("[Server] Initiating shutdown sequence...")
    if tool_manager_actor:
        try:
            await tool_manager_actor.stop.remote()
        except Exception as e:
            print(f"[Server] Note during ToolManagerActor stop: {e}")
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
            
            async def send_status(content: str, steps = None, stage: str = None, stage_params: dict = None):
                payload = {
                    "type": "status", 
                    "content": content,
                    "session_id": session_id
                }
                if steps is not None:
                    payload["steps"] = steps
                if stage is not None:
                    payload["stage"] = stage
                if stage_params is not None:
                    payload["stage_params"] = stage_params
                await websocket.send_json(payload)
            
            initial_steps = [
                {"id": "memory", "title": "Retrieve memory and context", "status": "running"},
                {"id": "plan", "title": "Analyze requirements and plan tasks", "status": "pending"}
            ]
            await send_status("Retrieving conversation memory and context...", initial_steps, stage="memory_retrieval", stage_params={})
            
            current_memory.add_turn("User", user_message)
            context_str = await current_memory.get_context_and_compress()
            
            initial_steps[0]["status"] = "completed"
            initial_steps[1]["status"] = "running"
            await send_status("Analyzing requirements and planning execution steps...", initial_steps, stage="planning", stage_params={})
            
            final_state = await kuugen_orchestrator.execute_task(
                user_message, 
                memory_context=context_str,
                status_callback=send_status
            )
            
            response_payload = {
                "type": "result",
                "reply": final_state.chat_reply,
                "news_report": final_state.news_report,
                "search_report_content": getattr(final_state, "search_report_content", None),
                "search_report_file": final_state.search_report_file,
                "translated_file": final_state.final_translated_file,
                "current_phase": final_state.current_phase,
                "execution_steps": getattr(final_state, "execution_steps", []),
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
