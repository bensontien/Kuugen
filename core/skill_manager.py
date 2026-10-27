import os
import sys
import importlib.util
from typing import Dict, Any, Optional
from core.state import AgentState

class SkillManager:
    """
    Manages discovery, dynamic loading, and execution of modular Skills in .kuugen/skills/.
    """
    SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".kuugen", "skills")
    _module_cache: Dict[str, Any] = {}

    @classmethod
    def list_available_skills(cls) -> Dict[str, Dict[str, str]]:
        """Scan .kuugen/skills/ for skill directories containing SKILL.md and run.py."""
        skills = {}
        if not os.path.exists(cls.SKILLS_DIR):
            return skills

        for entry in os.listdir(cls.SKILLS_DIR):
            skill_path = os.path.join(cls.SKILLS_DIR, entry)
            if os.path.isdir(skill_path):
                skill_md = os.path.join(skill_path, "SKILL.md")
                run_py = os.path.join(skill_path, "run.py")
                if os.path.exists(run_py):
                    description = "No description provided."
                    if os.path.exists(skill_md):
                        try:
                            with open(skill_md, "r", encoding="utf-8") as f:
                                content = f.read()
                                for line in content.splitlines():
                                    if line.startswith("description:"):
                                        description = line.replace("description:", "").strip()
                                        break
                        except Exception:
                            pass
                    skills[entry] = {
                        "name": entry,
                        "path": skill_path,
                        "description": description
                    }
        return skills

    @classmethod
    def load_skill_module(cls, skill_name: str):
        """Dynamically load the run.py module of a given skill."""
        if skill_name in cls._module_cache:
            return cls._module_cache[skill_name]

        skill_run_path = os.path.join(cls.SKILLS_DIR, skill_name, "run.py")
        if not os.path.exists(skill_run_path):
            raise FileNotFoundError(f"Skill script not found at {skill_run_path}")

        module_name = f"kuugen.skills.{skill_name}.run"
        spec = importlib.util.spec_from_file_location(module_name, skill_run_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module specification for {skill_name}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        cls._module_cache[skill_name] = module
        return module

    @classmethod
    async def execute_skill(
        cls, 
        skill_name: str, 
        state: AgentState, 
        llm: Any = None, 
        tool_manager: Any = None, 
        **kwargs
    ) -> AgentState:
        """Execute a skill via its run.py execute interface."""
        module = cls.load_skill_module(skill_name)
        if not hasattr(module, "execute"):
            raise AttributeError(f"Skill '{skill_name}' does not implement the required 'execute' async function.")

        return await module.execute(state=state, llm=llm, tool_manager=tool_manager, **kwargs)
