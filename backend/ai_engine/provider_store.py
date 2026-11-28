# -*- coding: utf-8 -*-
"""ProviderStore — CRUD + active-provider selection for media provider templates.

Provider-neutral: a provider "template" is a full descriptor (base_url, api_key,
model, capabilities, dialect flags, icon) stored in a portable `providers.json`.
The API key is Fernet-encrypted at rest (separate key file, 0600) — same pattern as
MCPManager (mcp_key.key). The active provider id is persisted; the media layer
resolves the active provider's credentials/dialect for generation.

Storage layout:
  providers.json  -> {"providers": [ {id, name, base_url, api_key_enc, model,
                                      capabilities: {image,video,audio},
                                      dialect: {extra_body_ref, v1_suffix, ...},
                                      default_voice, default_image_model, ...,
                                      icon: "openai" | "anthropic" | ...},
                                      ...],
                     "activeId": ""}

Provider-neutral: no provider names are hardcoded. New providers are added via
this store (or by editing providers.json), never by editing media.py.
"""
import os
import json
import stat

from typing import Optional

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - cryptography is a real dependency
    Fernet = None


class ProviderStore:
    """CRUD over provider templates with Fernet-encrypted api keys + active id."""

    # Provider-neutral: a provider template has a fixed field set. All dialect
    # flags are booleans/strings; capabilities are booleans. Unknown keys are
    # preserved (forward-compatible) — this is config, not code.
    _FIELDS = (
        "id", "name", "base_url", "model",
        "capabilities", "dialect", "default_voice", "default_image_model",
        "default_video_model", "default_audio_model", "note", "icon",
    )

    def __init__(self, path: str):
        self.path = path
        self.key_file = os.environ.get(
            "AMT_PROVIDER_KEY_FILE",
            os.path.join(os.path.dirname(os.path.abspath(path)), "providers.key"),
        )
        self.providers: list[dict] = []
        self.active_id: str = ""
        self._fkey: Optional[bytes] = self._load_or_create_key()
        self._load()

    # ---------- key management (Fernet) ----------
    def _load_or_create_key(self) -> Optional[bytes]:
        if Fernet is None:
            return None
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, "rb") as f:
                    return f.read()
            except Exception:
                return None
        key = Fernet.generate_key()
        fd = os.open(self.key_file, os.O_WRONLY | os.O_CREAT, stat.S_IRWXU)  # 0600
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key

    def _enc(self, api_key: str) -> str:
        """Encrypt an api key at rest. Empty key -> empty (nothing to store)."""
        if not api_key or Fernet is None or self._fkey is None:
            return ""
        try:
            return Fernet(self._fkey).encrypt(api_key.encode()).decode()
        except Exception:
            return ""

    def _dec(self, enc: str) -> str:
        """Decrypt a stored api key. Empty/corrupt -> '' (graceful)."""
        if not enc:
            return ""
        if Fernet is None or self._fkey is None:
            return ""
        try:
            return Fernet(self._fkey).decrypt(enc.encode()).decode()
        except Exception:
            return ""

    # ---------- persistence ----------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.providers = data.get("providers", [])
                self.active_id = data.get("activeId", "")
            except Exception:
                self.providers, self.active_id = [], ""

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {"providers": [], "activeId": self.active_id}
        for p in self.providers:
            d = {k: p.get(k) for k in p if k != "api_key_enc"}
            # Store the encrypted key only; never the plaintext at rest.
            if p.get("api_key_enc"):
                d["api_key_enc"] = p["api_key_enc"]
            payload["providers"].append(d)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ---------- CRUD ----------
    def list_public(self) -> list[dict]:
        """Public list: no raw api key, only hasKey + decrypted-on-read key for the active one."""
        out = []
        for p in self.providers:
            pub = {k: p.get(k) for k in self._FIELDS if k in p}
            pub["hasKey"] = bool(p.get("api_key_enc"))
            pub.pop("id", None)
            pub["id"] = p.get("id", "")
            out.append(pub)
        return out

    def get_active(self) -> Optional[dict]:
        """Return the active provider WITH its api key decrypted (for the media layer)."""
        if not self.active_id:
            return None
        for p in self.providers:
            if p.get("id") == self.active_id:
                d = {k: p.get(k) for k in p if k != "api_key_enc"}
                d["api_key"] = self._dec(p.get("api_key_enc", ""))
                return d
        return None

    def get(self, provider_id: str) -> Optional[dict]:
        for p in self.providers:
            if p.get("id") == provider_id:
                d = {k: p.get(k) for k in p if k != "api_key_enc"}
                d["api_key"] = self._dec(p.get("api_key_enc", ""))
                return d
        return None

    def add(self, template: dict, make_active: bool = False) -> dict:
        import uuid
        pid = template.get("id") or ("p_" + uuid.uuid4().hex[:12])
        p = {k: template.get(k) for k in template if k in self._FIELDS}
        p["id"] = pid
        # Encrypt the api key at rest; never store plaintext.
        p["api_key_enc"] = self._enc(template.get("api_key", ""))
        # Remove plaintext from the stored record.
        p.pop("api_key", None)
        p.setdefault("capabilities", {})
        p.setdefault("dialect", {})
        self.providers.append(p)
        if make_active or not self.active_id:
            self.active_id = pid
        self.save()
        return p

    def update(self, provider_id: str, updates: dict) -> Optional[dict]:
        for p in self.providers:
            if p.get("id") == provider_id:
                for k in self._FIELDS:
                    if k in updates and k != "id":
                        p[k] = updates[k]
                # Re-encrypt the api key only if a new plaintext was supplied.
                if "api_key" in updates and updates["api_key"]:
                    p["api_key_enc"] = self._enc(updates["api_key"])
                p.pop("api_key", None)
                self.save()
                return {k: p.get(k) for k in self._FIELDS if k in p}
        return None

    def delete(self, provider_id: str) -> bool:
        before = len(self.providers)
        self.providers = [p for p in self.providers if p.get("id") != provider_id]
        if len(self.providers) < before:
            if self.active_id == provider_id:
                self.active_id = self.providers[0]["id"] if self.providers else ""
            self.save()
            return True
        return False

    def set_active(self, provider_id: str) -> bool:
        if any(p.get("id") == provider_id for p in self.providers):
            self.active_id = provider_id
            self.save()
            return True
        return False

    def clear_active(self) -> None:
        self.active_id = ""
        self.save()
