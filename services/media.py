"""Voice aur image ko chat tak pahunchana, aur kharcha qaboo mein rakhna (har user ki roz ki hadd)."""
import asyncio
import time
from typing import Dict, Tuple

from ai.speech import SpeechError
from ai.vision import VisionError

IMAGE_CONTEXT = ("User ne chart ki tasveer bheji. Neeche AI vision ke observations hain (andaza, galat ho sakte hain; "
                 "bot ke apne indicators/analysis zyada bharosemand hain, observations ko sirf extra hint maanein):\n")


class MediaService:
    def __init__(self, speech, reader, chat, daily_limit: int = 20, clock=time.time):
        self.speech = speech
        self.reader = reader
        self.chat = chat
        self.daily_limit = daily_limit
        self.clock = clock
        self._used: Dict[Tuple[int, int], int] = {}

    def allow(self, user_id: int) -> bool:
        """Voice+image milakar roz ki hadd (UTC din). Memory mein hai, restart par reset."""
        day = int(self.clock() // 86400)
        self._used = {k: v for k, v in self._used.items() if k[1] == day}
        n = self._used.get((user_id, day), 0)
        if n >= self.daily_limit:
            return False
        self._used[(user_id, day)] = n + 1
        return True

    async def transcribe(self, audio: bytes) -> str:
        return await asyncio.to_thread(self.speech.transcribe, audio)

    async def image_reply(self, user_id: int, image: bytes, media_type: str, caption: str = "") -> str:
        try:
            notes = await asyncio.to_thread(self.reader.read, image, media_type, caption)
        except VisionError as e:
            return f"Tasveer parh nahi saka: {e}"
        text = ("[chart image] " + caption.strip()) if caption.strip() else "[chart image] is chart par kya nazar aa raha hai?"
        return await asyncio.to_thread(self.chat.reply_blocking, user_id, text[:2000], "", IMAGE_CONTEXT + notes)


__all__ = ["MediaService", "SpeechError", "VisionError"]
