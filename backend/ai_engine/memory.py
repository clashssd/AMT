"""Persistent AI memory module.

Extracts key facts from conversations and persists them so that
newer chats can build on context from earlier ones.
"""

import json
import os
import time
import httpx
from typing import Optional


class Memory:
    def __init__(self, path: str):
        self.path = path
        self.facts: list[dict] = []
        self.user_prefs: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.facts = data.get("facts", [])
                self.user_prefs = data.get("user_prefs", {})
            except Exception:
                self.facts = []
                self.user_prefs = {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"facts": self.facts, "user_prefs": self.user_prefs}, f, ensure_ascii=False, indent=2)

    def get_system_prompt_append(self) -> str:
        """Returns a text block to append to the system prompt with known facts."""
        if not self.facts:
            return ""
        lines = ["Вот что я знаю о пользователе и предыдущих беседах:"]
        for fact in self.facts[-20:]:
            lines.append(f"- {fact['text']}")
        return "\n".join(lines)

    def add_fact(self, text: str, chat_id: str = ""):
        """Manually add a fact (used by extract_facts)."""
        self.facts.append({
            "text": text,
            "chat_id": chat_id,
            "ts": int(time.time()),
        })
        self.save()

    async def extract_facts(
        self,
        user_msg: str,
        assistant_msg: str,
        base_url: str,
        api_key: str,
        model: str,
    ):
        """Use the model to extract 1-3 key facts from the conversation.

        Runs silently; errors are swallowed so the main chat is never blocked.
        """
        if not api_key or not base_url:
            return

        extraction_prompt = (
            "Извлеки из этой беседы 1-3 кл��чевых факта о пользователе или его предпочтениях. "
            "Верни только список фактов, по одному в строке, без нумерации. "
            "Если фактов нет — верни пустую строку.\n\n"
            f"Пользователь: {user_msg}\n"
            f"Ассистент: {assistant_msg}"
        )

        try:
            url = f"{base_url.rstrip('/')}/chat/completions"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": extraction_prompt}],
                        "max_tokens": 150,
                        "temperature": 0.1,
                    },
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                facts = [line.strip() for line in raw.splitlines() if line.strip() and len(line.strip()) > 5]
                for fact in facts[:3]:
                    self.add_fact(fact)
        except Exception:
            # Never let fact extraction break the main flow
            pass

    def wipe(self):
        """Remove all stored facts and prefs."""
        self.facts = []
        self.user_prefs = {}
        self.save()
