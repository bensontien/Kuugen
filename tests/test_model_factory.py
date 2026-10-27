import pytest
from factorys.model_factory import ModelFactory
from core.llm_client import OpenAICompatibleClient

def test_model_factory_local():
    config = {
        "provider": "vllm",
        "model_name": "Qwen/Qwen2.5-7B",
        "api_base": "http://localhost:8000/v1",
        "api_key": "empty",
        "timeout": 300
    }
    llm = ModelFactory.create_llm(config)
    assert isinstance(llm, OpenAICompatibleClient)
    assert llm.model == "Qwen/Qwen2.5-7B"
    assert llm.api_base == "http://localhost:8000/v1"
    assert llm.timeout == 300

def test_model_factory_openai():
    config = {
        "provider": "openai",
        "model_name": "gpt-4o",
        "api_key": "sk-12345",
        "timeout": 60
    }
    llm = ModelFactory.create_llm(config)
    assert isinstance(llm, OpenAICompatibleClient)
    assert llm.model == "gpt-4o"
    assert llm.api_base == "https://api.openai.com/v1"

def test_model_factory_openrouter():
    config = {
        "provider": "openrouter",
        "model_name": "anthropic/claude-3.5-sonnet",
        "api_key": "sk-or-12345",
        "timeout": 120,
        "app_title": "Custom App"
    }
    llm = ModelFactory.create_llm(config)
    assert isinstance(llm, OpenAICompatibleClient)
    assert llm.model == "anthropic/claude-3.5-sonnet"
    assert llm.api_base == "https://openrouter.ai/api/v1"
    assert llm.default_headers["X-Title"] == "Custom App"

def test_model_factory_unsupported():
    config = {
        "provider": "unsupported_xyz",
        "model_name": "xyz"
    }
    with pytest.raises(ValueError, match="Unsupported model provider"):
        ModelFactory.create_llm(config)
