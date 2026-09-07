import os
import json
import inspect
import asyncio
import ray
from core.state import AgentState, Plan, Task
from core.prompt_loader import PromptLoader 
from core.ray_manager import AgentActor, GenericAgentActor, ToolManagerActor, merge_states

class KuugenOrchestrator:
    def __init__(self, llm, registry, tool_manager=None, tool_manager_actor=None):
        self.llm = llm
        self.registry = registry
        self.tool_manager = tool_manager
        self.actors = {}
        self.tool_manager_actor = tool_manager_actor
        self._init_actors()

    def _init_actors(self):
        """Initialize Ray Actors using correct factory types and llm types"""
        if not ray.is_initialized():
            return

        print("[Orchestrator] Initializing Ray Cluster Components...")
        
        # Mapping from node name (in registry) to (agent_type, llm_type)
        node_agent_map = {
            "SearchPaperAgent": ("SearchPaperAgent", "external"),
            "TranslatorAgent": ("PDFTranslatorAgent", "translator"),
            "NewsAgent": ("NewsAgent", "external"),
            "ChatAgent": ("ChatAgent", "external"),
        }

        print("[Orchestrator] Initializing Ray Agent Actors (Lazy Init Mode)...")
        for name, node in self.registry._nodes.items():
            if name in node_agent_map:
                agent_type, llm_type = node_agent_map[name]
                self.actors[name] = AgentActor.remote(
                    agent_type=agent_type, 
                    llm_type=llm_type, 
                    tool_manager_actor=self.tool_manager_actor
                )
            else:
                # Handle plain functions like DownloadTool wrapper
                from core.ray_manager import FunctionActor
                self.actors[name] = FunctionActor.remote(name, node.executor)
        
        # Add a special actor for GenericAgent handling
        self.actors["GenericAgentActor"] = GenericAgentActor.remote(
            llm_type='external', 
            tool_manager_actor=self.tool_manager_actor
        )

    async def warm_up(self):
        """Warms up all initialized Ray Actors."""
        print("[Orchestrator] Warming up Ray Actors...")
        init_tasks = []
        
        # We now call initialize on ALL actors since we added dummy methods
        for name, actor in self.actors.items():
            try:
                init_tasks.append(actor.initialize.remote())
            except Exception as e:
                print(f"[Orchestrator] Warning: Failed to trigger init for {name}: {e}")
        
        if init_tasks:
            # Gather results to ensure they all complete
            await asyncio.gather(*[asyncio.wrap_future(t.to_task()) if hasattr(t, 'to_task') else t for t in init_tasks], return_exceptions=True)
            print(f"[Orchestrator] {len(init_tasks)} Ray Actors warmed up.")

    async def _generate_plan(self, user_prompt: str, memory_context: str = "") -> Plan:
        specialized_agents_desc = self.registry.get_all_descriptions()
        
        # Fetch the skill catalog + specific tool descriptions
        available_skills_desc = "None currently available."
        if self.tool_manager:
            static_catalog = PromptLoader.load_skill_catalog()
            try:
                # Use Ray Proxy to get dynamic tool list
                dynamic_tools = self.tool_manager.get_all_tool_descriptions()
                available_skills_desc = f"{static_catalog}\n\n[Specific Tools Currently Registered]:\n{dynamic_tools}"
            except Exception as e:
                print(f"[Orchestrator] Warning: Could not fetch dynamic tool descriptions: {e}")
                available_skills_desc = static_catalog

        # Load the base orchestrator prompt from the Markdown file
        base_prompt_template = PromptLoader.load_agent_prompt("orchestrator")
        
        # Inject the dynamic context into the prompt
        prompt = base_prompt_template.format(
            specialized_agents_desc=specialized_agents_desc,
            available_skills_desc=available_skills_desc,
            memory_context=memory_context if memory_context else "None",
            user_prompt=user_prompt
        )
        
        print("[Orchestrator] Thinking and planning tasks...")
        try:
            response = await self.llm.acomplete(prompt)
            raw_text = str(response).strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3].strip()
                
            plan_data = json.loads(raw_text)
            plan = Plan(**plan_data)
            return plan
        except Exception as e:
            print(f"Planning failed: {e}")
            return Plan(tasks=[])

    async def execute_task(self, user_prompt: str, search_source: str = "openalex", memory_context: str = "") -> AgentState:
        state = AgentState(user_topic=user_prompt, search_source=search_source)
        state.memory_context = memory_context
        os.makedirs("Papers", exist_ok=True)
        
        # Populate capability info for agents to use
        state.available_agents = self.registry.get_all_descriptions()
        if self.tool_manager:
            try:
                state.available_tools = self.tool_manager.get_all_tool_descriptions()
            except Exception as e:
                print(f"[Orchestrator] Warning: Could not fetch tool descriptions: {e}")
        
        state.plan = await self._generate_plan(user_prompt, memory_context)
        
        print("\n=== Current Task Execution Plan (Ray Parallel Enabled) ===")
        for t in state.plan.tasks:
            category_info = f"(Category: {getattr(t, 'required_category', 'None')})" if getattr(t, 'required_category', None) else ""
            deps_info = f"[Depends on: {t.depends_on}]" if t.depends_on else "[Independent]"
            print(f"  [{t.task_id}] {t.assigned_node} {category_info} {deps_info} -> {t.description}")
        print("===========================\n")

        # --- Ray Parallel Execution Logic ---
        completed_task_ids = set()
        pending_tasks = {t.task_id: t for t in state.plan.tasks}
        running_futures = {} # {future_id: task_id}

        while pending_tasks or running_futures:
            if state.is_aborted:
                break

            # 1. Identify tasks whose dependencies are met and are not already running
            to_start = []
            for tid, task in pending_tasks.items():
                if all(dep_id in completed_task_ids for dep_id in task.depends_on):
                    to_start.append(tid)

            # 2. Launch tasks in parallel using Ray
            for tid in to_start:
                task = pending_tasks.pop(tid)
                print(f"[Orchestrator] Launching parallel task {tid}: {task.assigned_node}")
                
                # Execute via Ray Actor if initialized, otherwise fallback to local
                if ray.is_initialized():
                    if task.assigned_node == "GenericAgent":
                        future = self.actors["GenericAgentActor"].run.remote(state, task.model_dump())
                    elif task.assigned_node in self.actors:
                        future = self.actors[task.assigned_node].run.remote(state)
                    else:
                        print(f"[Warning] Node {task.assigned_node} not in actors, running locally.")
                        future = self._run_local_task(task, state)
                else:
                    future = self._run_local_task(task, state)
                
                running_futures[future] = tid

            if not running_futures:
                if pending_tasks:
                    print(f"Warning: Deadlock detected! Pending tasks: {list(pending_tasks.keys())} but nothing running.")
                    break
                break

            # 3. Wait for at least one task to complete
            done_futures, _ = ray.wait(list(running_futures.keys()), num_returns=1, timeout=1.0)
            
            for df in done_futures:
                tid = running_futures.pop(df)
                try:
                    # Get result from Ray future
                    result_state = ray.get(df)
                    # Merge result back to main state
                    state = merge_states(state, result_state)
                    completed_task_ids.add(tid)
                    print(f"[Orchestrator] Task {tid} completed.")
                except Exception as e:
                    print(f"[Orchestrator] Task {tid} failed: {e}")
                    state.is_aborted = True

            # Short sleep to prevent tight loop if no tasks are ready
            await asyncio.sleep(0.1)

        state.current_phase = "finished"
        
        # --- Final Post-processing: Convert Simplified Chinese to Traditional Chinese ---
        from core.utils import converter
        if state.chat_reply:
            state.chat_reply = converter.to_traditional(state.chat_reply)
        if state.news_report:
            state.news_report = converter.to_traditional(state.news_report)
        if state.search_report_content:
            state.search_report_content = converter.to_traditional(state.search_report_content)
        if state.step_results:
            state.step_results = {k: converter.to_traditional(v) for k, v in state.step_results.items()}
            
        print("\n[Orchestrator] Plan execution completed!")
        return state

    async def _run_local_task(self, task, state):
        """Fallback local execution if Ray is not available or node not wrapped"""
        from agents.generic_agent import GenericAgent
        if task.assigned_node == "GenericAgent":
             temp_agent = GenericAgent(
                llm=self.llm,
                tool_manager=self.tool_manager,
                required_category=task.required_category,
                system_prompt=task.role_prompt if task.role_prompt else "Use tools.",
                task_id=task.task_id
            )
             return await temp_agent.run(state=state)
        else:
            node = self.registry.get_node(task.assigned_node)
            if node:
                res = node.executor(state=state)
                return await res if inspect.isawaitable(res) else res
        return state
