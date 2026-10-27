import httpx
from typing import Dict, Any, Optional

class LLMResponse:
    """Encapsulates the response from the LLM, maintaining compatibility with str(response)."""
    def __init__(self, text: str, raw: Optional[Dict[str, Any]] = None):
        self.text = text
        self.raw = raw or {}

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"LLMResponse(text={self.text!r})"

    def strip(self, *args, **kwargs) -> str:
        return self.text.strip(*args, **kwargs)

class OpenAICompatibleClient:
    """
    Lightweight, native asynchronous client for OpenAI-compatible REST APIs.
    Supports local vLLM, OpenAI, and OpenRouter without external framework overhead.
    """
    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str = "empty",
        timeout: float = 600.0,
        default_headers: Optional[Dict[str, str]] = None
    ):
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key or "empty"
        self.timeout = timeout
        self.default_headers = default_headers or {}
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=30.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
            )
        return self._client

    async def acomplete(self, prompt: str, **kwargs) -> LLMResponse:
        """
        Asynchronously send a completion request via /chat/completions endpoint.
        Returns an LLMResponse that can be directly converted to string via str(response).
        """
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            **self.default_headers
        }
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            **kwargs
        }

        client = self._get_client()
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(text="", raw=data)
            
        message = choices[0].get("message", {})
        content = message.get("content", "") or ""
        return LLMResponse(text=content, raw=data)

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        """Synchronous-like interface alias for compatibility."""
        return await self.acomplete(prompt, **kwargs)

    async def close(self):
        """Close the underlying HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
