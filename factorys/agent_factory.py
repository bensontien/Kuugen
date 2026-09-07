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

    def create_agent(self, agent_type: str, llm_type: str = 'local', **kwargs) -> Any:
        # 1. Extract tool_manager immediately to prevent leaking into Workflow kwargs
        tool_mgr = kwargs.pop('tool_manager', None)
        
        # 2. Retrieve the corresponding LLM instance
        target_llm = self.get_llm(llm_type)
        
        # 3. Calculate the final timeout
        timeout = kwargs.pop('timeout', self.default_timeout)

        # 4. Instantiate the Agent with on-demand lazy imports
        if agent_type == 'SearchPaperAgent':
            from agents.searchpaper_agent import SearchPaperAgent
            return SearchPaperAgent(
                llm=target_llm, 
                timeout=timeout,
                verbose=True, 
                **kwargs
            )
            
        elif agent_type == 'PDFTranslatorAgent':
            from agents.translator_agent import PDFTranslatorAgent
            trans_timeout = timeout if timeout > 1200 else 3600
            actual_llm = target_llm if llm_type != 'local' else self.get_llm('translator')
            
            return PDFTranslatorAgent(
                llm=actual_llm, 
                timeout=trans_timeout,
                verbose=True, 
                **kwargs
            )
            
        elif agent_type == 'NewsAgent':
            from agents.news_agent import NewsAgent
            return NewsAgent(
                llm=target_llm,
                tool_manager=tool_mgr,
                timeout=timeout,
                verbose=True, 
                **kwargs
            )
        
        elif agent_type == 'ChatAgent':
            from agents.chat_agent import ChatAgent
            return ChatAgent(
                llm=target_llm, 
                tool_manager=tool_mgr,
                timeout=timeout, 
                verbose=True, 
                **kwargs
            )
            
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

    def get_agent(self, agent_type: str, llm_type: str = 'local', **kwargs) -> Any:
        return self.create_agent(agent_type, llm_type=llm_type, **kwargs)
