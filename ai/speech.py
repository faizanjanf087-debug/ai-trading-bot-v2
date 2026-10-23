"""Voice note -> text (speech-to-text). OpenAI-compatible /audio/transcriptions (Groq ya OpenAI).

Audio sirf transcription ke liye teesri party service ko jata hai aur bot use save nahi karta; sirf text aage chalta hai.
"""
from typing import Optional

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "whisper-large-v3-turbo"
# Roman Urdu/English alfaaz ka hint, taake nateeja Roman likhai ke qareeb rahe aur trading ke lafz sahi aayein
PROMPT = "Gold ka signal do, total status batao, tp hit howa, loss ho gaya, XAUUSD BTCUSD EURUSD analysis."


class SpeechError(Exception):
    pass


def _post_file(url: str, headers: dict, files: dict, data: dict) -> dict:
    import requests

    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    if resp.status_code >= 400:
        raise SpeechError(f"Speech service HTTP {resp.status_code}: {resp.text[:150]}")
    return resp.json()


class Transcriber:
    def __init__(self, api_key: str = "", base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL,
                 http_post=_post_file):
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.http_post = http_post

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, audio: bytes, filename: str = "voice.ogg", mime: str = "audio/ogg") -> str:
        """Blocking. Async code mein asyncio.to_thread ke saath chalayein."""
        if not self.api_key:
            raise SpeechError("STT_API_KEY set nahi hai.")
        if not audio:
            raise SpeechError("Khali audio.")
        data = self.http_post(
            f"{self.base_url}/audio/transcriptions",
            {"Authorization": f"Bearer {self.api_key}"},
            {"file": (filename, audio, mime)},
            {"model": self.model, "prompt": PROMPT, "response_format": "json", "temperature": "0"},
        )
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str):
            raise SpeechError(f"Transcription ka jawab samajh nahi aaya: {str(data)[:150]}")
        return text.strip()
