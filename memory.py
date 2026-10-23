"""Chat ki yaad: aakhri kuch messages + purane messages ka summary (database mein)."""
import time
from typing import List

from ai import prompts
from ai.deepseek_client import AIError
from db.chat import ChatRepo


class ChatMemory:
    def __init__(self, repo: ChatRepo, client, recent: int = 10, summarize_after: int = 30, clock=time.time):
        self.repo = repo
        self.client = client
        self.recent = recent
        self.summarize_after = summarize_after
        self.clock = clock

    def history_messages(self, user_id: int) -> List[dict]:
        msgs = []
        summary = self.repo.get_summary(user_id)
        if summary:
            msgs.append({"role": "system", "content": f"User ke saath pichli baat-cheet ka summary:\n{summary}"})
        msgs += [{"role": m["role"], "content": m["content"]} for m in self.repo.recent(user_id, self.recent)]
        return msgs

    def remember(self, user_id: int, user_text: str, reply: str) -> None:
        ts = int(self.clock())
        self.repo.add(user_id, "user", user_text, ts)
        self.repo.add(user_id, "assistant", reply, ts)

    def maybe_summarize(self, user_id: int) -> bool:
        """Messages bohot barh jayein to purane wale summary mein badal do (blocking)."""
        total = self.repo.count(user_id)
        if total <= self.summarize_after:
            return False
        old = self.repo.oldest(user_id, total - self.recent)
        if not old:
            return False
        try:
            text = self.client.chat(prompts.summary_prompt(self.repo.get_summary(user_id) or "", old),
                                    temperature=0.2, max_tokens=400)
        except AIError:
            return False
        self.repo.set_summary(user_id, text, int(self.clock()))
        self.repo.delete_ids([m["id"] for m in old])
        return True
