"""Менеджер нескольких API-ключей с автопереключением.

Позволяет держать несколько ключей (от разных провайдеров или аккаунтов).
При лимите (HTTP 429) у текущего ключа система автоматически переключается
на следующий доступный. Также можно явно выбрать ключ для новой сессии.

Структура keys.json:
{
  "keys": [
    {
      "id": "k1",
      "label": "Мой провайдер",
      "baseUrl": "https://api.example.com/v1",
      "apiKey": "ВАШ_КЛЮЧ",
      "model": "model-name",
      "temperature": 0.7,
      "maxTokens": 4096,
      "contextWindow": 128000,
      "httpProxy": "",
      "httpsProxy": "",
      "systemPrompt": "",
      "cooldownUntil": 0        # unix ts — когда ключ снова доступен
    }
  ],
  "activeKeyId": "k1",
  "roundRobin": false           # если true — переключаем по кругу, не ждём кулдаун
}

Безопасность: keys.json хранит ключи в открытом виде на диске (как settings.json).
API отдаёт только `hasApiKey`/label — сами ключи не возвращаются клиенту.
"""

import json
import os
import time
from typing import Optional


class KeyManager:
    def __init__(self, path: str):
        self.path = path
        self.keys: list[dict] = []
        self.active_key_id: str = ""
        self.round_robin: bool = False
        self._load()

    # ---------- persistence ----------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.keys = data.get("keys", [])
                self.active_key_id = data.get("activeKeyId", "")
                self.round_robin = data.get("roundRobin", False)
            except Exception:
                self.keys, self.active_key_id, self.round_robin = [], "", False

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {"keys": self.keys, "activeKeyId": self.active_key_id, "roundRobin": self.round_robin},
                f, ensure_ascii=False, indent=2
            )

    # ---------- CRUD ----------
    def list_public(self) -> list[dict]:
        """Общедоступный список (без самих ключей)."""
        out = []
        for k in self.keys:
            pub = {fkey: k.get(fkey) for fkey in
                   ["id", "label", "baseUrl", "model", "temperature", "maxTokens",
                    "contextWindow", "httpProxy", "httpsProxy", "systemPrompt"]}
            pub["hasKey"] = bool(k.get("apiKey"))
            pub["cooldownUntil"] = k.get("cooldownUntil", 0)
            out.append(pub)
        return out

    def add_key(self, key: dict, make_active: bool = False) -> dict:
        if not key.get("id"):
            key["id"] = "k_" + os.urandom(4).hex()
        key.setdefault("cooldownUntil", 0)
        self.keys.append(key)
        if make_active or (not self.active_key_id):
            self.active_key_id = key["id"]
        self.save()
        return key

    def update_key(self, key_id: str, updates: dict) -> Optional[dict]:
        for k in self.keys:
            if k["id"] == key_id:
                # Не позволяем случайно обнулить кулдаун извне
                updates.pop("cooldownUntil", None)
                k.update(updates)
                self.save()
                return k
        return None

    def delete_key(self, key_id: str) -> bool:
        before = len(self.keys)
        self.keys = [k for k in self.keys if k["id"] != key_id]
        if len(self.keys) < before:
            if self.active_key_id == key_id:
                self.active_key_id = self.keys[0]["id"] if self.keys else ""
            self.save()
            return True
        return False

    def set_active(self, key_id: str) -> bool:
        if any(k["id"] == key_id for k in self.keys):
            self.active_key_id = key_id
            self.save()
            return True
        return False

    # ---------- resolve next key (auto-switch logic) ----------
    def get_key(self, key_id: Optional[str] = None) -> Optional[dict]:
        """Вернуть конкретный ключ или ак��ивный."""
        target = key_id or self.active_key_id
        return next((k for k in self.keys if k["id"] == target), None)

    def next_available_key(self, exclude_ids: Optional[set] = None) -> Optional[dict]:
        """Следующий доступный ключ (не в кулдауне, не в exclude).

        Если round_robin — ищем после активного; иначе — первый доступный.
        """
        exclude = exclude_ids or set()
        now = time.time()
        available = [k for k in self.keys
                     if k["id"] not in exclude
                     and k.get("apiKey")
                     and k.get("cooldownUntil", 0) <= now]
        if not available:
            return None
        if self.round_robin:
            # найти индекс активного и начать с него (по кругу)
            try:
                idx = next(i for i, k in enumerate(self.keys) if k["id"] == self.active_key_id)
            except StopIteration:
                idx = -1
            ordered = [self.keys[(idx + 1 + i) % len(self.keys)] for i in range(len(self.keys))]
            for k in ordered:
                if k["id"] not in exclude and k.get("apiKey") and k.get("cooldownUntil", 0) <= now:
                    return k
            return None
        return available[0]

    def mark_rate_limited(self, key_id: str, retry_after: int = 30):
        """Пометить ключ в кулдаун после 429."""
        k = next((x for x in self.keys if x["id"] == key_id), None)
        if k:
            k["cooldownUntil"] = int(time.time() + max(retry_after, 30))
            self.save()

    def rotate_active(self, current_key_id: str, exclude: Optional[set] = None) -> Optional[str]:
        """Переключить активный ключ на следующий доступный. Возвращает новый id."""
        nxt = self.next_available_key(exclude_ids={current_key_id} | (exclude or set()))
        if nxt:
            self.active_key_id = nxt["id"]
            self.save()
            return nxt["id"]
        return None
