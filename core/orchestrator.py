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
        self._llm = llm
        self.registry = registry
        self.tool_manager = tool_manager
        self.actors = {}
        self.tool_manager_actor = tool_manager_actor
        self._init_actors()

    @property
    def llm(self):
        if callable(self._llm):
            self._llm = self._llm()
        return self._llm

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
            await asyncio.gather(*init_tasks, return_exceptions=True)
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

    async def execute_task(
        self, 
        user_prompt: str, 
        search_source: str = "openalex", 
        memory_context: str = "",
        status_callback = None
    ) -> AgentState:
        async def report_progress(content: str, steps: list = None, stage: str = None, stage_params: dict = None):
            if not status_callback:
                return
            try:
                sig = inspect.signature(status_callback)
                param_count = len(sig.parameters)
                if param_count >= 4:
                    res = status_callback(content, steps, stage, stage_params)
                elif param_count >= 2:
                    res = status_callback(content, steps)
                else:
                    res = status_callback(content)
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                print(f"[Orchestrator Progress Warning] {e}")

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
        
        steps_info = [
            {"id": "plan", "title": "Analyze requirements and plan tasks", "status": "running"}
        ]
        await report_progress("Analyzing requirements and planning execution steps...", steps_info, stage="planning", stage_params={})

        state.plan = await self._generate_plan(user_prompt, memory_context)
        
        steps_info[0]["status"] = "completed"
        task_lookup = {}
        total_tasks = len(state.plan.tasks)

        if not state.plan.tasks:
            await report_progress("Planning finished, no further tasks needed.", steps_info, stage="plan_empty", stage_params={})
        else:
            for t in state.plan.tasks:
                task_lookup[t.task_id] = t
                steps_info.append({
                    "id": str(t.task_id),
                    "title": t.description or f"Execute {t.assigned_node}",
                    "node": t.assigned_node,
                    "status": "pending"
                })
            steps_info.append({
                "id": "finalize",
                "title": "Format and finalize response",
                "status": "pending"
            })
            await report_progress(
                f"Plan generated ({total_tasks} tasks total), preparing parallel execution...", 
                steps_info, 
                stage="plan_ready", 
                stage_params={"total": total_tasks}
            )

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
                for s in steps_info:
                    if s["id"] == str(tid):
                        s["status"] = "running"

                # Execute via Ray Actor if initialized, otherwise fallback to local
                if ray.is_initialized() and (task.assigned_node in self.actors or task.assigned_node == "GenericAgent"):
                    if task.assigned_node == "GenericAgent":
                        future = self.actors["GenericAgentActor"].run.remote(state, task.model_dump())
                    else:
                        future = self.actors[task.assigned_node].run.remote(state)
                else:
                    if ray.is_initialized():
                        print(f"[Warning] Node {task.assigned_node} not in actors, running locally.")
                    future = asyncio.create_task(self._run_local_task(task, state))
                
                running_futures[future] = tid

            if to_start:
                current_running = [task_lookup[t_id] for t_id in running_futures.values() if t_id in task_lookup]
                if len(current_running) > 1:
                    tasks_summary = ", ".join([f"{t.description} ({t.assigned_node})" for t in current_running])
                    await report_progress(
                        f"Executing in parallel ({len(current_running)} tasks): {tasks_summary}...", 
                        steps_info, 
                        stage="executing_parallel", 
                        stage_params={"count": len(current_running), "tasks": tasks_summary}
                    )
                elif len(current_running) == 1:
                    t = current_running[0]
                    await report_progress(
                        f"Executing [{len(completed_task_ids)+1}/{total_tasks}]: {t.description} ({t.assigned_node})...", 
                        steps_info, 
                        stage="executing_single", 
                        stage_params={"current": len(completed_task_ids)+1, "total": total_tasks, "task": t.description, "node": t.assigned_node}
                    )

            if not running_futures:
                if pending_tasks:
                    print(f"Warning: Deadlock detected! Pending tasks: {list(pending_tasks.keys())} but nothing running.")
                    break
                break

            # 3. Wait for at least one task to complete (handling both Ray ObjectRefs and asyncio Tasks)
            ray_refs = [f for f in running_futures.keys() if hasattr(ray, 'ObjectRef') and isinstance(f, ray.ObjectRef)]
            async_tasks = [f for f in running_futures.keys() if f not in ray_refs]

            done_futures = []
            if ray_refs:
                done_ray, _ = ray.wait(ray_refs, num_returns=1, timeout=0.2)
                done_futures.extend(done_ray)
            if async_tasks and not done_futures:
                done_async, _ = await asyncio.wait(async_tasks, timeout=0.2, return_when=asyncio.FIRST_COMPLETED)
                done_futures.extend(done_async)
            
            for df in done_futures:
                tid = running_futures.pop(df)
                task_obj = task_lookup.get(tid)
                try:
                    # Get result from Ray future or asyncio Task
                    if hasattr(ray, 'ObjectRef') and isinstance(df, ray.ObjectRef):
                        result_state = ray.get(df)
                    else:
                        result_state = await df if inspect.isawaitable(df) else df.result()
                    
                    # Merge result back to main state
                    state = merge_states(state, result_state)
                    completed_task_ids.add(tid)
                    for s in steps_info:
                        if s["id"] == str(tid):
                            s["status"] = "completed"
                    task_desc = task_obj.description if task_obj else f"Task {tid}"
                    await report_progress(
                        f"Completed [{len(completed_task_ids)}/{total_tasks}]: {task_desc}", 
                        steps_info, 
                        stage="task_completed", 
                        stage_params={"current": len(completed_task_ids), "total": total_tasks, "task": task_desc}
                    )
                    print(f"[Orchestrator] Task {tid} completed.")
                except Exception as e:
                    print(f"[Orchestrator] Task {tid} failed: {e}")
                    state.is_aborted = True
                    for s in steps_info:
                        if s["id"] == str(tid):
                            s["status"] = "failed"
                    await report_progress(
                        f"Task failed [{tid}]: {e}", 
                        steps_info, 
                        stage="task_failed", 
                        stage_params={"tid": tid, "error": str(e)}
                    )

            # Short sleep to prevent tight loop if no tasks are ready
            await asyncio.sleep(0.1)

        state.current_phase = "finished"
        
        for s in steps_info:
            if s["id"] == "finalize":
                s["status"] = "running"
        await report_progress("Tasks completed, finalizing response...", steps_info, stage="finalizing", stage_params={})

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
            
        for s in steps_info:
            if s["id"] == "finalize":
                s["status"] = "completed"
        state.execution_steps = steps_info
        await report_progress("Processing finished, rendering response...", steps_info, stage="finished", stage_params={})

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
