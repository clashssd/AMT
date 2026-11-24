"""Взаимодействие с системой — оркестратор + гейтинг.

Это МОДУЛЬ-КАРКАС (инфраструктура). По требованию пользователя конкретные
агенты и скиллы НЕ прописываются — создаётся только:
  * оркестратор взаимодействия с системой (свой системный блок)
  * хранилище привязанных к нему агентов и их скиллов (max 5 на агента)
  * ГЕЙТИНГ: без включённого тумблера в чате все sysinteraction-агенты/скиллы
    НЕ применяются (build_system_prompt возвращает "").
  * БЕЗОПАСНОСТЬ: оркестратор не имеет прямых сетевых/файловых инструментов.
    Все действия идут через ToolSandbox (read_file/list_dir/run_command/
    open_url) — только разрешённые каталоги, только whitelist-команды,
    только http/https. Никакого слива данных наружу. Каждое действие логируется.
    Если ToolSandbox.enabled=False — взаимодействие недоступно даже при включённом
    тумблере (авто-гейт).

Структура файла sysinteraction.json:
{
  "enabled": false,                       # глобальный гейт (сверху, до тумблера чата)
  "orchestrator": {
      "id": "sys_orchestrator",
      "name": "Оркестратор взаимодействия",
      "prompt": "...",                   # системный блок
      "tools_allow": ["read_file","list_dir","run_command","open_url"]
  },
  "agents": [
      {
          "id": "sys_agent_1",
          "name": "...",
          "description": "...",
          "systemPrompt": "...",          # пока пустой каркас
          "folder": "sysinteraction",     # папка в хранилище
          "skills": ["s1","s2"]          # max 5
      }
  ],
  "skills": [
      { "id": "s1", "name": "...", "prompt": "...", "enabled": true,
        "folder": "sysinteraction", "agentId": "sys_agent_1" }
  ]
}
"""

import json
import os
from typing import Optional


MAX_SKILLS_PER_AGENT = 5


class SysInteractionOrchestrator:
    def __init__(self, path: str):
        self.path = path
        self.enabled: bool = False
        self.orchestrator: dict = {
            "id": "sys_orchestrator",
            "name": "Оркестратор взаимодействия с системой",
            "prompt": (
                "Ты — оркестратор взаимодействия с системой. Ты координируешь агентов "
                "и скиллы, которые безопасно взаимодействуют с окружением пользователя. "
                "Правила безопасности (абсолютные): "
                "1) НИКОГДА не сливай данные наружу (никакой exfiltration). "
                "2) НИКОГДА не повреждай систему, файлы или данные пользователя. "
                "3) Действуй только через разрешённые инструменты (read, list, command из "
                "whitelist, open_url http/https). "
                "4) Каждое действие должно быть логировано. "
                "5) Если действие неясно или рискованно — спроси пользователя, не угадывай. "
                "Пока конкретные агенты и скиллы не определены — работай в режиме каркаса."
            ),
            "tools_allow": ["read_file", "list_dir", "run_command", "open_url"],
        }
        self.agents: list[dict] = []
        self.skills: list[dict] = []
        self._load()

    # ---------- persistence ----------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.enabled = bool(data.get("enabled", False))
                if isinstance(data.get("orchestrator"), dict):
                    self.orchestrator = data["orchestrator"]
                self.agents = data.get("agents", []) or []
                self.skills = data.get("skills", []) or []
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "enabled": self.enabled,
                    "orchestrator": self.orchestrator,
                    "agents": self.agents,
                    "skills": self.skills,
                },
                f, ensure_ascii=False, indent=2,
            )

    # ---------- гейтинг: главный механизм ----------
    def is_active(self, chat_toggle: bool, tools_enabled: bool = False) -> bool:
        """Взаимодействие активно только если:
        - глобальный гейт enabled=True
        - тумблер в чате chat_toggle=True
        - ToolSandbox включён (tools_enabled)
        Иначе — False (ни один sysinteraction-агент/скилл не применяется).
        """
        return bool(self.enabled and chat_toggle and tools_enabled)

    def build_system_prompt(self, active: bool) -> str:
        """Возвращает системный блок оркестратора ТОЛЬКО если active=True.
        Иначе "" — гейт: без включения ничего не применяется.
        """
        if not active:
            return ""
        parts = []
        if self.orchestrator.get("prompt"):
            parts.append(
                "[Оркестратор взаимодействия с системой]\n"
                + self.orchestrator["prompt"]
            )
        # Привязанные агенты + их скиллы (max 5) — только при active
        for a in self.agents:
            if a.get("systemPrompt"):
                parts.append(f"[Агент: {a.get('name', a['id'])}]\n{a['systemPrompt']}")
            for sid in self.get_agent_skills(a["id"]):
                sk = self._find_skill(sid)
                if sk and sk.get("prompt"):
                    parts.append(f"[Скилл: {sk.get('name', sid)}]\n{sk['prompt']}")
        return "\n\n".join(parts)

    # ---------- агенты ----------
    def list_agents(self) -> list[dict]:
        return self.agents

    def get_agent(self, agent_id: str) -> Optional[dict]:
        return next((a for a in self.agents if a["id"] == agent_id), None)

    def add_agent(self, agent: dict) -> dict:
        if not agent.get("id"):
            agent["id"] = "sys_agent_" + os.urandom(4).hex()
        agent.setdefault("folder", "sysinteraction")
        agent.setdefault("skills", [])
        self.agents.append(agent)
        self.save()
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        before = len(self.agents)
        self.agents = [a for a in self.agents if a["id"] != agent_id]
        # скиллы этого агента тоже удаляем
        self.skills = [s for s in self.skills if s.get("agentId") != agent_id]
        if len(self.agents) < before:
            self.save()
            return True
        return False

    # ---------- скиллы (max 5 на агента) ----------
    def list_skills(self) -> list[dict]:
        return self.skills

    def get_agent_skills(self, agent_id: str) -> list[str]:
        """Скиллы агента, лимит MAX_SKILLS_PER_AGENT."""
        a = self.get_agent(agent_id)
        if not a:
            return []
        return list(a.get("skills", []))[:MAX_SKILLS_PER_AGENT]

    def _find_skill(self, skill_id: str) -> Optional[dict]:
        return next((s for s in self.skills if s["id"] == skill_id), None)

    def add_skill(self, skill: dict, agent_id: str) -> dict:
        """Добавляет скилл и привязывает к агенту (если < 5)."""
        a = self.get_agent(agent_id)
        if not a:
            raise ValueError("Агент не найден: " + agent_id)
        if not skill.get("id"):
            skill["id"] = "sys_skill_" + os.urandom(4).hex()
        skill.setdefault("folder", "sysinteraction")
        skill["agentId"] = agent_id
        # лимит 5 скиллов на агента
        existing = a.get("skills", [])
        if skill["id"] not in existing and len(existing) >= MAX_SKILLS_PER_AGENT:
            raise ValueError(
                f"Превышен лимит {MAX_SKILLS_PER_AGENT} скиллов для агента "
                + a.get("name", agent_id)
            )
        self.skills.append(skill)
        if skill["id"] not in a["skills"]:
            a["skills"].append(skill["id"])
        self.save()
        return skill

    def delete_skill(self, skill_id: str) -> bool:
        before = len(self.skills)
        self.skills = [s for s in self.skills if s["id"] != skill_id]
        for a in self.agents:
            if skill_id in a.get("skills", []):
                a["skills"] = [x for x in a["skills"] if x != skill_id]
        if len(self.skills) < before or True:
            self.save()
            return True
        return False

    # ---------- конфиг для фронтенда ----------
    def public_config(self, tools_enabled: bool) -> dict:
        """Всё для хранилища + флаг «доступно сейчас?»."""
        return {
            "enabled": self.enabled,
            "tools_enabled": tools_enabled,
            # активность = enabled AND tools_enabled (тумблер чата — пер-чат)
            "available": bool(self.enabled and tools_enabled),
            "orchestrator": self.orchestrator,
            "agents": [
                {**a, "skills": self.get_agent_skills(a["id"])}
                for a in self.agents
            ],
            "skills": self.skills,
            "max_skills_per_agent": MAX_SKILLS_PER_AGENT,
        }
