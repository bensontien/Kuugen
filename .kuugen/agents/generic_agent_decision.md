{system_prompt}

[Skill Category Rules & Guidelines]:
{skill_details}

[Available Tools in Your Assigned Category]:
{tool_descriptions}

[Accumulated Context from Previous Steps]:
{accumulated_context}

[Overall User Request]: 
{user_input}

INSTRUCTIONS:
1. Review the [Accumulated Context]. If it ALREADY contains the EXACT information needed for your specific task, you may process the context to answer directly.
2. [CRITICAL] If the context DOES NOT contain the information, or if you need to perform an action to fulfill your role, you MUST call a tool. Do NOT guess or make up answers.
3. To call a tool, output strictly in this JSON format and NOTHING ELSE:
```json
{{
    "action": "tool_name",
    "arguments": {{"arg_name": "value"}}
}}