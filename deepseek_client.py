"""DeepSeek (OpenAI-compatible API). Sirf text jata hai (indicator values), chart image nahi."""
from typing import List

URL = "https://api.deepseek.com/chat/completions"


class AIError(Exception):
    pass


def _post(url: str, headers: dict, payload: dict) -> dict:
    import requests

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise AIError(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


class DeepSeekClient:
    def __init__(self, api_key: str, model: str = "deepseek-chat", http_post=_post):
        self.api_key = api_key
        self.model = model
        self.http_post = http_post

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: List[dict], temperature: float = 0.3, max_tokens: int = 700) -> str:
        """Blocking call. Async code mein asyncio.to_thread ke saath chalayein."""
        if not self.api_key:
            raise AIError("DEEPSEEK_API_KEY set nahi hai.")
        data = self.http_post(
            URL,
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            {"model": self.model, "messages": messages, "temperature": temperature,
             "max_tokens": max_tokens, "stream": False},
        )
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            raise AIError(f"DeepSeek ka jawab samajh nahi aaya: {str(data)[:200]}")
