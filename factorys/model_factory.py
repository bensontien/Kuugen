from typing import Dict
from core.llm_client import OpenAICompatibleClient

class ModelFactory:
    @staticmethod
    def create_llm(config: Dict) -> OpenAICompatibleClient:
        """
        Return the native OpenAICompatibleClient instance based on the provided configuration dictionary.
        """
        provider = config.get("provider", "vllm")
        
        if provider in ("vllm", "local"):
            return OpenAICompatibleClient(
                model=config["model_name"],
                api_base=config["api_base"],
                api_key=config.get("api_key", "empty"),
                timeout=config.get("timeout", 600)
            )
            
        elif provider == "openai":
            api_base = config.get("api_base") or "https://api.openai.com/v1"
            return OpenAICompatibleClient(
                model=config["model_name"],
                api_key=config["api_key"],
                api_base=api_base,
                timeout=config.get("timeout", 60)
            )
            
        elif provider == "openrouter":
            api_base = config.get("api_base") or "https://openrouter.ai/api/v1"
            headers = {
                "HTTP-Referer": config.get("http_referer", "https://github.com/bensontien/Kuugen"),
                "X-Title": config.get("app_title", "Kuugen Assistant"),
            }
            return OpenAICompatibleClient(
                model=config["model_name"],
                api_base=api_base,
                api_key=config["api_key"],
                timeout=config.get("timeout", 120),
                default_headers=headers
            )
        
        else:
            raise ValueError(f"Unsupported model provider: {provider}")
