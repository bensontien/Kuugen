# Kuugen AI Assistant (v2.0)

Kuugen is a high-performance, enterprise-grade AI assistant system built on a **Microservices & Multi-Agent Architecture**. It leverages **Ray** for parallel task orchestration, **LlamaIndex** for agentic workflows, and the **Model Context Protocol (MCP)** for standardized tool execution.

The system features a clean separation between the "Brain" (LLM reasoning and planning) and the "Muscle" (Tool execution and environment interaction), following a **Prompts-as-Code** philosophy.

---

## System Architecture

![System Architecture](AC.png)

### Key Architectural Pillars
-   **Ray-Powered Parallel DAG Scheduling**: Complex user queries are analyzed and decomposed into a Directed Acyclic Graph (DAG) of dependent/independent tasks (`depends_on`). Ready tasks execute concurrently across a Ray worker cluster via a hybrid scheduler that dynamically polls Ray `ObjectRef`s and native `asyncio.Task`s using `ray.wait` and `asyncio.wait(FIRST_COMPLETED)`, preventing deadlocks.
-   **Real-Time Step Tracking & Event Streaming**: Fine-grained execution stages (`memory_retrieval`, `planning`, `plan_ready`, `executing_parallel`, `executing_single`, `task_completed`, `finalizing`, `finished`) and individual step transitions (`pending`, `running`, `completed`, `failed`) are broadcast via WebSocket in real time for live UI visualization.
-   **Eager Background Warm-Up & Sub-Second Startup**: During the FastAPI lifespan startup, actors are warmed up in a non-blocking background task. Combined with lazy module importing and LLM instance caching in `AgentFactory` and `ModelFactory`, the API gateway achieves sub-second cold starts without latency spikes on initial requests.
-   **Brain-Muscle Decoupling via Ray Tool Actor**: AI agent workflows (LlamaIndex) are isolated from physical tool execution via `ToolManagerActor` and `RayToolManagerProxy`. The tool server runs as an independent FastMCP process over stdio, eliminating Python GIL bottlenecks and cross-process object serialization issues.
-   **Dual-Track Routing & Progressive Tool Disclosure**: 
    -   **Specialized Agents**: High-efficiency, multi-step workflows tuned for specific domains (`SearchPaperAgent`, `NewsAgent`, `PDFTranslatorAgent`, `ChatAgent`).
    -   **Generic Agents**: Dynamic runtime agents instantiated on-the-fly for custom tasks, discovering tool definitions progressively through categorized skill schemas (`web_scraping`, `system_ops`, `general`) to keep context windows clean.
-   **Prompts-as-Code & Dynamic Hot-Reloading**: All orchestrator planning templates, agent personas, and skill documentation are maintained in `.kuugen/` as Markdown files. `PromptLoader` reads these dynamically at runtime, allowing prompt tuning and behavioral changes without code modification or service restarts.
-   **Adaptive Memory Management with LLM Compression**: `MemoryManager` maintains dialogue continuity using a sliding window for recent turns, automatically triggering LLM-based recursive summarization into Traditional Chinese when context boundaries are reached.
-   **Full-Stack Internationalization (i18n) & Automated OpenCC Conversion**: Kuugen UI features instant bilingual switching (`zh-TW` and `en-US`), while the backend integrates OpenCC to guarantee all AI-generated text is delivered in Traditional Chinese.

---

## Core Features

-   **Autonomous DAG Planning**: Uses a high-level LLM planner to break down complex goals into a dependency-aware execution graph with parallel scheduling.
-   **Real-Time Execution Step Visualizer**: WebSocket-driven live feedback displaying active, completed, and pending steps with collapsible stage accordions.
-   **Capability Discovery**: Dynamically injects available tools and specialized agents into the state, allowing agents (such as `ChatAgent`) to accurately describe Kuugen's capabilities.
-   **Standardized MCP & Host OS Control**: Full support for Model Context Protocol (FastMCP) plus secure Windows PowerShell execution from WSL with safety keyword filtering.
-   **Progressive Tool Disclosure**: Agents dynamically request skill categories on demand, keeping the context window clean and minimizing hallucinations.
-   **Automatic Traditional Chinese Conversion**: Integrates OpenCC to automatically convert all Simplified Chinese outputs to Traditional Chinese across all agents.
-   **Adaptive Conversation Memory**: Sliding-window history with intelligent LLM context summarization.
-   **Hybrid LLM Engine**: Seamlessly switch between distributed local vLLM on Ray, OpenRouter, and OpenAI.
-   **Bilingual React UI**: Modern React 19 + Vite frontend with live WebSocket streaming, dark/light theme switching, and GitHub Flavored Markdown rendering.

---

## Project Structure

```text
Agents/
├── .kuugen/                    # Intelligence Layer (Prompts-as-Code)
│   ├── agents/                 # Personas for Orchestrator and Specialized Agents
│   │   ├── chat_agent.md
│   │   ├── generic_agent_decision.md
│   │   ├── generic_agent_summary.md
│   │   ├── news_agent.md
│   │   └── orchestrator.md
│   └── skills/                 # Skill catalogs & category definitions
│       ├── catalog.md
│       ├── system_ops.md
│       └── web_scraping.md
│
├── agents/                     # Implementation Layer (LlamaIndex Workflows)
│   ├── chat_agent.py           # Conversational & capability-aware agent
│   ├── generic_agent.py        # Dynamic agent with progressive tool disclosure
│   ├── news_agent.py           # Real-time news aggregation, scraping & analysis
│   ├── searchpaper_agent.py    # Academic paper search & ranking (OpenAlex / ArXiv)
│   └── translator_agent.py     # High-precision chunked PDF translation workflow
│
├── core/                       # Kernel & Infrastructure Layer
│   ├── mcp_client.py           # FastMCP client implementation (stdio communication)
│   ├── memory.py               # Sliding-window context memory & LLM auto-compression
│   ├── orchestrator.py         # Dynamic DAG planner, parallel task scheduler & event streamer
│   ├── prompt_loader.py        # Prompts-as-code loader (.kuugen Markdown reader)
│   ├── ray_manager.py          # Ray Actor definitions, tool proxy & state merger
│   ├── registry.py             # Node registry for specialized agent/tool discovery
│   ├── state.py                # Capability-aware agent state & task data models
│   ├── tool_manager.py         # Multi-adapter tool registry (SkillTool, CLITool, MCPTool)
│   └── utils.py                # Utilities (OpenCC Simplified-to-Traditional converter)
│
├── factorys/                   # Abstraction & Factory Layer
│   ├── agent_factory.py        # Agent creation, dependency injection & lazy module loading
│   └── model_factory.py        # Unified LLM provider interface (vLLM, OpenRouter, OpenAI)
│
├── kuugen-ui/                  # Frontend Layer (React 19 + Vite + Modern UI)
│   ├── src/
│   │   ├── context/            # LanguageContext for dynamic i18n
│   │   ├── hooks/              # useTranslation custom hook
│   │   ├── locales/            # Translation resources (en-US, zh-TW)
│   │   ├── App.jsx             # Main chat window, step tracker & WebSocket client
│   │   ├── App.css             # Responsive theme styling (Dark / Light)
│   │   └── main.jsx            # Application entry point & context provider wrapper
│   └── package.json
│
├── server.py                   # FastAPI Gateway, lifespan manager & WebSocket endpoint
├── tools_server.py             # FastMCP Tool Server (The Muscle - scraper, CLI, PDF)
├── config.py                   # Environment configuration & provider settings
├── vllm_ray_launcher.py        # Local GPU vLLM OpenAI server wrapped in Ray Actor
├── start_vllm.py               # Standalone vLLM server launch script
└── download_model.py           # HuggingFace model downloader utility
```

---

## Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js & npm (for UI)
- Ray (installed via pip)

### 2. Environment Setup
Create a `.env` file in the root:
```env
# Intelligence
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL_NAME=google/gemma-2-9b-it

# Local Muscle (vLLM)
VLLM_API_BASE=http://localhost:8000/v1
DEFAULT_LOCAL_MODEL_PATH=/path/to/your/model
```

### 3. Installation
```bash
pip install -r requirements.txt
cd kuugen-ui && npm install && cd ..
```

### 4. Running the System
```bash
# Start the Backend
uvicorn server:app --host 0.0.0.0 --port 8080

# In another terminal, start the UI
cd kuugen-ui
npm run dev
```

---

## Extension Guide

### Adding a New Skill
1.  Add a new tool function in `tools_server.py` using `@mcp.tool()`.
2.  Update `.kuugen/skills/catalog.md` to include the new tool in a category.
3.  The `GenericAgent` will automatically discover it during execution.

### Creating a Specialized Agent
1.  Inherit from existing agent patterns in `agents/`.
2.  Define a new persona in `.kuugen/agents/your_agent.md`.
3.  Register the agent in `factorys/agent_factory.py` and `server.py` registry.

---

## License
MIT License. Created by Ching-Yang Tien.
