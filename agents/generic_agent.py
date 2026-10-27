import json
from core.base_agent import BaseAgent
from core.state import AgentState
from core.prompt_loader import PromptLoader

class GenericAgent(BaseAgent):
    def __init__(
        self,
        llm,
        tool_manager=None,
        required_category: str = None,
        system_prompt: str = "",
        task_id: int = 0,
        timeout: float = 3600.0,
        **kwargs
    ):
        super().__init__(llm=llm, tool_manager=tool_manager, timeout=timeout, **kwargs)
        self.required_category = required_category 
        self.system_prompt = system_prompt
        self.task_id = task_id 

    async def run(self, state: AgentState) -> AgentState:
        user_input = state.user_topic
        
        print(f"[GenericAgent - Step {self.task_id}] Spawning custom agent with category: {self.required_category}")
        
        # 1. Get tool descriptions for the assigned category
        tool_descriptions = "None"
        if self.tool_manager and self.required_category:
            tool_descriptions = self.tool_manager.get_schemas_by_category(self.required_category)
        elif self.tool_manager:
            tool_descriptions = self.tool_manager.get_all_schemas()

        if tool_descriptions == "No tools found for this category." or not tool_descriptions:
            tool_descriptions = "No tools available for the requested category. You must answer using ONLY the provided context."

        # 2. Combine history records
        accumulated_context = ""
        if state.step_results:
            for past_task_id, past_result in sorted(state.step_results.items()):
                if past_task_id < self.task_id:
                    accumulated_context += f"\n--- [Result from Step {past_task_id}] ---\n{past_result}\n"

        # 3. Load Skill Details (dynamically read category rules)
        skill_details = "No specific rules provided for this category."
        if self.required_category:
            skill_details = PromptLoader.load_skill_details(self.required_category)

        # 4. Decision Prompt (inject skill_details into template)
        decision_prompt_template = PromptLoader.load_agent_prompt("generic_agent_decision")
        decision_prompt = decision_prompt_template.format(
            system_prompt=self.system_prompt,
            skill_details=skill_details,
            tool_descriptions=tool_descriptions,
            accumulated_context=accumulated_context if accumulated_context else "None. You are the first step.",
            user_input=user_input
        )
        
        try:
            print("[GenericAgent] Analyzing request and context...")
            response = await self.llm.acomplete(decision_prompt)
            res_text = str(response).strip()
            
            # Attempt to parse JSON tool call
            action_data = None
            if "```json" in res_text:
                json_str = res_text.split("```json")[1].split("```")[0].strip()
                action_data = json.loads(json_str)
            elif res_text.startswith("{") and "action" in res_text:
                action_data = json.loads(res_text)

            # 5. Execute task and generate result
            step_output = ""
            if action_data and "action" in action_data:
                tool_name = action_data["action"]
                tool_args = action_data.get("arguments", {})
                
                print(f"[GenericAgent] Calling Tool via Manager: {tool_name} with args: {tool_args}")
                tool_result = await self.tool_manager.execute(tool_name, **tool_args)
                print("[GenericAgent] Tool execution complete, summarizing...")
                
                # 6. Summary Prompt (load from Markdown)
                summary_prompt_template = PromptLoader.load_agent_prompt("generic_agent_summary")
                summary_prompt = summary_prompt_template.format(
                    tool_name=tool_name,
                    tool_result=str(tool_result)[:5000],
                    system_prompt=self.system_prompt
                )
                
                final_response = await self.llm.acomplete(summary_prompt)
                step_output = str(final_response)
                
            else:
                print("[GenericAgent] No tool called, returning direct answer based on context.")
                step_output = res_text

            # 7. Write the result to the scratchpad and update chat reply
            state.step_results[self.task_id] = step_output
            state.chat_reply = step_output 

        except Exception as e:
            print(f"[GenericAgent] Execution failed: {e}")
            error_msg = f"Task execution failed: {e}"
            state.step_results[self.task_id] = error_msg
            state.chat_reply = error_msg
            
        return state
