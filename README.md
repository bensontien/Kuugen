# Kuugen AI Assistant (v2.0)

Kuugen is a high-performance, enterprise-grade AI assistant system built on a **Microservices & Multi-Agent Architecture**. It leverages **Ray** for parallel task orchestration, **Native Async Workflows** for agentic execution, and the **Model Context Protocol (MCP)** for standardized tool execution.

The system features a clean separation between the "Brain" (LLM reasoning and planning) and the "Muscle" (Tool execution and environment interaction), following a **Prompts-as-Code** philosophy with **zero heavy blackbox agent framework dependencies**.

---

## System Architecture

![System Architecture](AC.png)

### Key Architectural Pillars
-   **Ray-Powered Parallel DAG Scheduling**: Complex user queries are analyzed and decomposed into a Directed Acyclic Graph (DAG) of dependent/independent tasks (`depends_on`). Ready tasks execute concurrently across a Ray worker cluster via a hybrid scheduler that dynamically polls Ray `ObjectRef`s and native `asyncio.Task`s using `ray.wait` and `asyncio.wait(FIRST_COMPLETED)`, preventing deadlocks.
-   **Unified Autonomous ReAct Agent**: All agentic tasks converge into a single, highly capable ReAct agent (`GenericAgent`). It executes an iterative `Thought -> Action -> Observation` loop with multi-turn reasoning, automatic error recovery, and a 10-step runaway guardrail, eliminating redundant agent wrappers.
-   **Dynamic Multi-Instance Ray Actor Dispatch**: The orchestrator dynamically spawns or assigns tasks to `GenericAgentActor` instances on Ray, unlocking true distributed multi-agent parallelism for simultaneous web searches, paper retrieval, and data processing.
-   **Modular Skills Architecture**: Specialized domain capabilities are decoupled into independent skill packages under `.kuugen/skills/` (such as `search_paper`, `pdf_translator`, and `news_search`), each featuring self-contained pipelines (`run.py`) and dynamic documentation (`SKILL.md`) managed via `SkillManager` and registered as `SkillTool`.
-   **Native Async Client & Zero LlamaIndex Footprint**: Built entirely on standard Python `asyncio` and `httpx` (`OpenAICompatibleClient`), completely eliminating heavy third-party framework overhead, reducing memory consumption, and providing sub-second cold starts.
-   **Real-Time Step Tracking & Event Streaming**: Fine-grained execution stages (`memory_retrieval`, `planning`, `plan_ready`, `executing_parallel`, `executing_single`, `task_completed`, `finalizing`, `finished`) and individual step transitions (`pending`, `running`, `completed`, `failed`) are broadcast via WebSocket in real time for live UI visualization.
-   **Brain-Muscle Decoupling via Ray Tool Actor**: Agent reasoning is isolated from physical tool execution via `ToolManagerActor` and `RayToolManagerProxy`. The tool server runs as an independent FastMCP process over stdio, eliminating Python GIL bottlenecks and cross-process object serialization issues.
-   **Progressive Tool Disclosure**: Agents dynamically request skill categories on demand (`academic_research`, `academic_translation`, `web_scraping`, `system_ops`), keeping context windows minimal and eliminating tool hallucinations.
-   **Prompts-as-Code & Dynamic Hot-Reloading**: All orchestrator planning templates, agent personas, and skill documentation are maintained in `.kuugen/` as Markdown files. `PromptLoader` reads these dynamically at runtime, allowing prompt tuning and behavioral changes without code modification or service restarts.
-   **Adaptive Memory Management with LLM Compression**: `MemoryManager` maintains dialogue continuity using a sliding window for recent turns, automatically triggering LLM-based recursive summarization into Traditional Chinese when context boundaries are reached.
-   **Full-Stack Internationalization (i18n) & Automated OpenCC Conversion**: Kuugen UI features instant bilingual switching (`zh-TW` and `en-US`), while the backend integrates OpenCC to guarantee all AI-generated text is delivered in Traditional Chinese.

---

## Core Features

-   **Autonomous DAG Planning**: Uses a high-level LLM planner to break down complex goals into a dependency-aware execution graph with parallel scheduling.
-   **Autonomous ReAct Problem Solving**: Multi-turn reasoning loop (`Thought -> Action -> Observation`) with dynamic tool execution and self-correction.
-   **Real-Time Execution Step Visualizer**: WebSocket-driven live feedback displaying active, completed, and pending steps with collapsible stage accordions.
-   **Modular Skill Packages**:
    -   `search_paper`: Deep academic paper search across ArXiv and OpenAlex top journals, 6-dimension scoring, citation snowballing, and review synthesis.
    -   `pdf_translator`: Academic PDF layout extraction, chunked parallel translation, and formula preservation.
    -   `news_search`: Real-time dual-language Google News RSS search, content scraping, and trend analysis.
-   **Standardized MCP & Host OS Control**: Full support for Model Context Protocol (FastMCP) plus secure Windows PowerShell execution from WSL with safety keyword filtering.
-   **LaTeX Math Rendering via KaTeX**: Frontend renders inline `$formula$` and block `$$formula$$` mathematical notation with robust error boundary handling.
-   **Progressive Tool Disclosure**: Dynamic category-based tool schema injection to maintain minimal LLM context overhead.
-   **Automatic Traditional Chinese Conversion**: Seamless OpenCC integration converting all Simplified Chinese responses into Traditional Chinese.
-   **Adaptive Conversation Memory**: Sliding-window history with intelligent LLM context summarization.
-   **Hybrid LLM Engine**: Seamlessly switch between distributed local vLLM on Ray, OpenRouter, and OpenAI.
-   **Modern React UI**: React 19 + Vite frontend with live WebSocket streaming, dark/light theme switching, and GitHub Flavored Markdown rendering.
-   **Automated CI Pipeline**: GitHub Actions workflow running 23 comprehensive unit tests across all layers on push and pull requests.

---

## Project Structure

```text
Kuugen/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI workflow (pytest across Python 3.12)
│
├── .kuugen/                    # Intelligence Layer (Prompts-as-Code & Modular Skills)
│   ├── agents/                 # Orchestrator planning templates & system prompts
│   │   └── orchestrator.md
│   └── skills/                 # Modular Skill Packages & Category Schemas
│       ├── catalog.md          # Global skill category index
│       ├── system_ops.md       # System operations & CLI tool definitions
│       ├── web_scraping.md     # Web scraping & content fetching schemas
│       ├── search_paper/       # Academic literature search, scoring & snowballing
│       │   ├── SKILL.md
│       │   └── run.py
│       ├── pdf_translator/     # Academic PDF extraction & chunked translation
│       │   ├── SKILL.md
│       │   └── run.py
│       └── news_search/        # Lightweight Google News RSS dual-language aggregation
│           ├── SKILL.md
│           └── run.py
│
├── agents/                     # Implementation Layer (Autonomous ReAct Agent)
│   └── generic_agent.py        # Unified ReAct agent (Thought -> Action -> Observation)
│
├── core/                       # Kernel & Infrastructure Layer
│   ├── base_agent.py           # Native BaseAgent abstract base class
│   ├── llm_client.py           # Native OpenAI-compatible asynchronous HTTP client (httpx)
│   ├── mcp_client.py           # FastMCP client implementation (stdio communication)
│   ├── memory.py               # Sliding-window context memory & LLM auto-compression
│   ├── orchestrator.py         # Dynamic DAG planner, parallel task scheduler & WebSocket streamer
│   ├── prompt_loader.py        # Prompts-as-code loader (.kuugen Markdown reader)
│   ├── ray_manager.py          # Ray Actor definitions (GenericAgentActor, ToolManagerActor, proxy)
│   ├── registry.py             # Node registry for dynamic execution dispatch
│   ├── skill_manager.py        # Dynamic modular skill discovery & execution manager
│   ├── state.py                # Capability-aware agent state, Plan, and Task data models
│   ├── tool_manager.py         # Multi-adapter tool registry (SkillTool, CLITool, MCPTool)
│   └── utils.py                # Utilities (OpenCC Simplified-to-Traditional converter)
│
├── factorys/                   # Abstraction & Factory Layer
│   ├── agent_factory.py        # Agent instantiation & lazy LLM instance caching
│   └── model_factory.py        # Unified LLM provider interface (vLLM, OpenRouter, OpenAI)
│
├── kuugen-ui/                  # Frontend Layer (React 19 + Vite + KaTeX)
│   ├── src/
│   │   ├── context/            # LanguageContext for dynamic i18n
│   │   ├── hooks/              # useTranslation custom hook
│   │   ├── locales/            # Translation resources (en-US, zh-TW)
│   │   ├── App.jsx             # Main chat window, KaTeX LaTeX rendering & WebSocket client
│   │   ├── App.css             # Responsive theme styling (Dark / Light)
│   │   └── main.jsx            # Application entry point & context provider wrapper
│   ├── package.json
│   └── vite.config.js
│
├── tests/                      # Automated Test Suite (100% Native Pytest)
│   ├── test_agents.py          # ReAct multi-turn loop, tool invocation & step guards
│   ├── test_base_agent.py      # BaseAgent contract validation
│   ├── test_llm_client.py      # Async HTTP client & OpenAI response formatting
│   ├── test_model_factory.py   # ModelFactory provider configuration & caching
│   ├── test_orchestrator.py    # DAG plan generation & parallel Ray task dispatch
│   └── test_skill_manager.py   # Dynamic skill discovery & execution pipeline
│
├── server.py                   # FastAPI Gateway, lifespan manager & WebSocket endpoint
├── tools_server.py             # FastMCP Tool Server (The Muscle - web scraper, CLI, PDF)
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

### 4. Running the Tests
```bash
# Execute the native test suite (23 tests across 6 test suites)
pytest
# or
python3 -m pytest
```

### 5. Running the System
```bash
# Start the Backend Gateway & Ray Orchestrator
uvicorn server:app --host 0.0.0.0 --port 8080

# In another terminal, start the Frontend UI
cd kuugen-ui
npm run dev
```

---

## Extension Guide

### Adding a Modular Skill
1.  Create a new directory under `.kuugen/skills/<skill_name>/`.
2.  Add a `SKILL.md` specifying YAML frontmatter (`name`, `description`) and documentation.
3.  Add a `run.py` implementing `async def run(state: AgentState, llm: Any, tool_manager: Any, **kwargs) -> AgentState`.
4.  Register the skill in `core/tool_manager.py` using `SkillTool` and specify its category (or allow `SkillManager` to execute it dynamically).

### Adding a FastMCP Tool
1.  Add a new tool function in `tools_server.py` using the `@mcp.tool()` decorator.
2.  Update `.kuugen/skills/catalog.md` or the corresponding markdown file in `.kuugen/skills/` with the new tool definition.
3.  `ToolManagerActor` will automatically discover the tool over MCP stdio protocol and make it accessible to `GenericAgent`.

---

## License
MIT License. Created by Ching-Yang Tien.
