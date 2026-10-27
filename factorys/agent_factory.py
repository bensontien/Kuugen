from typing import Any, Optional, Dict
from config import LLM_LOCAL_CONFIG, LLM_OPENROUTER_CONFIG, LLM_TRANSLATOR_CONFIG
from factorys.model_factory import ModelFactory

class AgentFactory:
    """
    Universal Agent Factory.
    Manages creation, dependency injection, and instance caching for all agents.
    Uses lazy loading to accelerate process startup and minimize memory/import overhead.
    """
    
    def __init__(self):
        self._llm_cache: Dict[str, Any] = {}
        self.default_timeout = LLM_LOCAL_CONFIG.get("timeout", 1200)

    @property
    def local_llm(self) -> Any:
        if 'local' not in self._llm_cache:
            self._llm_cache['local'] = ModelFactory.create_llm(LLM_LOCAL_CONFIG)
        return self._llm_cache['local']

    @property
    def translator_llm(self) -> Any:
        if 'translator' not in self._llm_cache:
            self._llm_cache['translator'] = ModelFactory.create_llm(LLM_TRANSLATOR_CONFIG)
        return self._llm_cache['translator']

    @property
    def external_llm(self) -> Any:
        if 'external' not in self._llm_cache:
            self._llm_cache['external'] = ModelFactory.create_llm(LLM_OPENROUTER_CONFIG)
        return self._llm_cache['external']

    def get_llm(self, llm_type: str = 'local') -> Any:
        """Retrieve the LLM instance of the specified type on demand."""
        if llm_type == 'local':
            return self.local_llm
        elif llm_type == 'translator':
            return self.translator_llm
        elif llm_type == 'external':
            return self.external_llm
        else:
            raise ValueError(f"Unknown LLM type: {llm_type}")

    def create_agent(self, agent_type: str = 'GenericAgent', llm_type: str = 'local', **kwargs) -> Any:
        tool_mgr = kwargs.pop('tool_manager', None)
        target_llm = self.get_llm(llm_type)
        timeout = kwargs.pop('timeout', self.default_timeout)

        from agents.generic_agent import GenericAgent
        category = kwargs.pop('required_category', None)
        role_prompt = kwargs.pop('role_prompt', kwargs.pop('system_prompt', ''))
        
        return GenericAgent(
            llm=target_llm,
            tool_manager=tool_mgr,
            required_category=category,
            system_prompt=role_prompt,
            timeout=timeout,
            max_steps=10,
            verbose=True,
            **kwargs
        )

    def get_agent(self, agent_type: str = 'GenericAgent', llm_type: str = 'local', **kwargs) -> Any:
        return self.create_agent(agent_type, llm_type=llm_type, **kwargs)
