import pytest
import unittest.mock as mock
import httpx
from core.llm_client import LLMResponse, OpenAICompatibleClient

def test_llm_response_properties():
    data = {"id": "chatcmpl-123"}
    resp = LLMResponse(text="  Hello World!  ", raw=data)
    assert resp.text == "  Hello World!  "
    assert str(resp) == "  Hello World!  "
    assert resp.strip() == "Hello World!"
    assert resp.raw == data
    assert repr(resp) == "LLMResponse(text='  Hello World!  ')"

@pytest.mark.asyncio
async def test_openai_compatible_client_init():
    client = OpenAICompatibleClient(
        model="gpt-4o",
        api_base="https://api.openai.com/v1/",
        api_key="sk-test",
        timeout=30.0,
        default_headers={"X-Custom": "TestValue"}
    )
    assert client.model == "gpt-4o"
    assert client.api_base == "https://api.openai.com/v1"
    assert client.api_key == "sk-test"
    assert client.timeout == 30.0
    assert client.default_headers["X-Custom"] == "TestValue"
    await client.close()

@pytest.mark.asyncio
async def test_openai_compatible_client_acomplete():
    client = OpenAICompatibleClient(
        model="test-model",
        api_base="http://localhost:8000/v1",
        api_key="empty"
    )

    mock_resp_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "This is a test answer from native client."
                }
            }
        ]
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_resp_data,
        request=httpx.Request("POST", "http://localhost:8000/v1/chat/completions")
    )

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await client.acomplete("Hello")

        assert isinstance(result, LLMResponse)
        assert str(result) == "This is a test answer from native client."
        assert result.text == "This is a test answer from native client."
        mock_post.assert_awaited_once()

    await client.close()
