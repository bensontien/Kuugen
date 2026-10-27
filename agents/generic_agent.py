import json
from typing import Optional, Dict, Any, List
from core.base_agent import BaseAgent
from core.state import AgentState
from core.prompt_loader import PromptLoader
from core.skill_manager import SkillManager

class GenericAgent(BaseAgent):
    """
    Autonomous ReAct (Reasoning + Acting) Agent.
    Executes a multi-turn Thought -> Action -> Observation loop with a maximum step guard (default 10).
    Can autonomously invoke tools and skills or return direct conversational answers.
    """
    def __init__(
        self,
        llm,
        tool_manager=None,
        required_category: Optional[str] = None,
        system_prompt: str = "",
        task_id: int = 0,
        max_steps: int = 10,
        timeout: float = 3600.0,
        **kwargs
    ):
        super().__init__(llm=llm, tool_manager=tool_manager, timeout=timeout, **kwargs)
        self.required_category = required_category 
        self.system_prompt = system_prompt or "You are an autonomous AI problem-solving agent."
        self.task_id = task_id 
        self.max_steps = max_steps

    def _parse_action(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract tool call action data from LLM response text."""
        try:
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
                if isinstance(data, dict) and "action" in data:
                    return data
            elif text.startswith("{") and "action" in text:
                data = json.loads(text)
                if isinstance(data, dict) and "action" in data:
                    return data
            elif "{" in text and '"action"' in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start != -1 and end > start:
                    data = json.loads(text[start:end])
                    if isinstance(data, dict) and "action" in data:
                        return data
        except Exception:
            pass
        return None

    async def _execute_action(self, action_data: Dict[str, Any], state: AgentState) -> str:
        """Dispatch action to SkillManager or ToolManager."""
        tool_name = action_data.get("action", "")
        tool_args = action_data.get("arguments", {})
        if not isinstance(tool_args, dict):
            tool_args = {}

        print(f"[GenericAgent - Step {self.task_id}] Executing action: {tool_name} with args: {tool_args}")
        
        # 1. Check if tool is a Skill in SkillManager
        available_skills = SkillManager.list_available_skills()
        if tool_name in available_skills:
            try:
                res_state = await SkillManager.execute_skill(
                    skill_name=tool_name,
                    state=state,
                    llm=self.llm,
                    tool_manager=self.tool_manager,
                    **tool_args
                )
                # Extract relevant text output from state
                if tool_name == "search_paper" and res_state.search_report_content:
                    return res_state.search_report_content
                elif tool_name == "pdf_translator" and res_state.final_translated_file:
                    return f"Translation saved to {res_state.final_translated_file}"
                elif tool_name == "news_search" and res_state.news_report:
                    return res_state.news_report
                elif res_state.chat_reply:
                    return res_state.chat_reply
                return f"Skill '{tool_name}' executed successfully."
            except Exception as e:
                return f"Error executing skill '{tool_name}': {e}"

        # 2. Otherwise dispatch to ToolManager
        if self.tool_manager:
            try:
                result = await self.tool_manager.execute(tool_name, state=state, llm=self.llm, **tool_args)
                return str(result)
            except Exception as e:
                return f"Error executing tool '{tool_name}': {e}"

        return f"Error: Tool '{tool_name}' not available and no ToolManager attached."

    async def run(self, state: AgentState) -> AgentState:
        user_input = state.user_topic
        print(f"[GenericAgent - Step {self.task_id}] Starting ReAct loop (Category: {self.required_category}, Max Steps: {self.max_steps})")

        # 1. Gather tool descriptions
        tool_descriptions = "No tools available."
        if self.tool_manager and self.required_category and self.required_category != "general":
            tool_descriptions = self.tool_manager.get_schemas_by_category(self.required_category)
            if tool_descriptions == "No tools found for this category." or not tool_descriptions:
                tool_descriptions = self.tool_manager.get_all_schemas()
        elif self.tool_manager:
            tool_descriptions = self.tool_manager.get_all_schemas()

        # 2. Gather skill details / guidelines
        skill_details = "None."
        if self.required_category:
            skill_details = PromptLoader.load_skill_details(self.required_category)

        # 3. Gather past step results
        accumulated_context = ""
        if state.step_results:
            for past_id, past_res in sorted(state.step_results.items()):
                if past_id < self.task_id:
                    accumulated_context += f"\n--- [Result from Step {past_id}] ---\n{past_res}\n"

        # 4. Construct base system prompt
        base_system = f"""{self.system_prompt}

[Skill Category Rules & Guidelines]:
{skill_details}

[Available Tools & Skills]:
{tool_descriptions}

[Autonomous ReAct Execution Rules]:
You operate in a multi-step Think -> Action -> Observation loop (Maximum {self.max_steps} steps).
1. In each step, you can explain your reasoning (Thought).
2. If you need to perform an action or retrieve information, output a JSON markdown block:
```json
{{
    "action": "tool_name",
    "arguments": {{"arg_name": "arg_value"}}
}}
```
3. If no tool is needed (such as answering a conversational question, analyzing existing context, or providing the final summary), output your Final Answer directly without any JSON tool call.
"""

        conversation_history: List[Dict[str, str]] = []
        final_answer = ""

        # 5. Execute ReAct Loop (up to max_steps)
        for step_idx in range(1, self.max_steps + 1):
            # Assemble current prompt
            history_str = ""
            if conversation_history:
                history_str = "\n".join([f"[{turn['role'].upper()}]: {turn['content']}" for turn in conversation_history])

            prompt = f"""{base_system}

[Overall User Request]:
{user_input}

[Accumulated Context from Previous Steps]:
{accumulated_context if accumulated_context else "None"}

[Current Interaction History]:
{history_str if history_str else "Beginning of task."}

[Step {step_idx}/{self.max_steps}]: Express your Thought, followed by either a tool call in ```json``` block or your Final Answer directly.
"""
            try:
                response = await self.llm.acomplete(prompt)
                res_text = str(response).strip()
            except Exception as e:
                print(f"[GenericAgent - Step {self.task_id}] LLM invocation failed on step {step_idx}: {e}")
                final_answer = f"Error during reasoning: {e}"
                break

            action_data = self._parse_action(res_text)

            if action_data:
                # Model called a tool
                conversation_history.append({"role": "assistant", "content": res_text})
                obs = await self._execute_action(action_data, state)
                obs_truncated = obs[:4000] + ("\n...[Truncated]" if len(obs) > 4000 else "")
                conversation_history.append({"role": "user", "content": f"[Observation from {action_data.get('action')}]:\n{obs_truncated}"})
            else:
                # Model produced final answer without tool calls
                print(f"[GenericAgent - Step {self.task_id}] Final answer reached in {step_idx} step(s).")
                final_answer = res_text
                break
        else:
            # Reached max steps limit
            print(f"[GenericAgent - Step {self.task_id}] Reached max steps limit ({self.max_steps}), consolidating response...")
            summary_prompt = f"""Based on the following interaction history, provide the final comprehensive response to the user's request:
User Request: {user_input}

History:
{history_str}

Final Answer:"""
            try:
                final_resp = await self.llm.acomplete(summary_prompt)
                final_answer = str(final_resp).strip()
            except Exception:
                final_answer = res_text

        # 6. Record results into AgentState
        state.step_results[self.task_id] = final_answer
        state.chat_reply = final_answer
        return state
