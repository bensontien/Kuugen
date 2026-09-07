import os

class PromptLoader:
    BASE_DIR = ".kuugen"

    @classmethod
    def load_agent_prompt(cls, agent_name: str) -> str:
        path = os.path.join(cls.BASE_DIR, "agents", f"{agent_name}.md")
        return cls._read_file(path, f"You are a helpful AI named {agent_name}.")

    @classmethod
    def load_skill_catalog(cls) -> str:
        path = os.path.join(cls.BASE_DIR, "skills", "catalog.md")
        return cls._read_file(path, "No skills catalog defined.")

    @classmethod
    def load_skill_details(cls, category: str) -> str:
        path = os.path.join(cls.BASE_DIR, "skills", f"{category}.md")
        return cls._read_file(path, f"Use tools in the {category} category carefully.")

    @staticmethod
    def _read_file(filepath: str, default: str) -> str:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            print(f"[Warning] Prompt file not found: {filepath}")
            return default