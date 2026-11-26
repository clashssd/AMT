from dataclasses import dataclass


@dataclass
class ChatProfile:
    chat_mode: str
    key_id: str
    api_key: str
    base_url: str
    model: str
    system_prompt_suffix: str = ""


def key_role(key_id: str) -> str:
    """Return role for a key if key manager exposes it; otherwise general."""
    key_id = (key_id or "").strip()
    if not key_id:
        return "general"
    keys_mgr = globals().get("keys_mgr")
    if keys_mgr is None:
        return "general"
    key = getattr(keys_mgr, "get_key", None)
    if callable(key):
        candidate = key(key_id) or {}
        return str(candidate.get("role", "general") or "general")
    return "general"


def _active_coding_key(keys_mgr=None):
    if keys_mgr is None:
        keys_mgr = globals().get("keys_mgr")
    if keys_mgr is None:
        return None
    for k in getattr(keys_mgr, "keys", []) or []:
        if str(k.get("role", "general") or "general") == "coding":
            return k
    return None


def resolve_chat_profile(request, keys_mgr=None, server_settings=None):
    chat_mode = (getattr(request, "chat_mode", "general") or "general").strip() or "general"
    key_id = (getattr(request, "key_id", "") or "").strip()
    settings = getattr(request, "settings", None)

    base_url = str(getattr(settings, "effective_base_url", "") or "")
    api_key = str(getattr(settings, "effective_api_key", "") or "")
    model = str(getattr(settings, "effective_model", "") or "")
    suffix = ""

    if keys_mgr is None:
        keys_mgr = globals().get("keys_mgr")
    if server_settings is None:
        server_settings = globals().get("server_settings")

    coding_settings_key = str(getattr(server_settings, "codingKey", "") or "").strip()
    coding_settings_base = str(getattr(server_settings, "codingBaseUrl", "") or "").strip()
    coding_settings_model = str(getattr(server_settings, "codingModel", "") or "").strip()

    if chat_mode == "coding":
        suffix = "\n\n[CODING PROFILE] Stay inside the requested project root, inspect files before editing, show diffs before writes, and run commands/tests only when needed."

        if key_id:
            key = keys_mgr.get_key(key_id) if keys_mgr else None
            if key and key.get("apiKey"):
                api_key = str(key.get("apiKey"))
                base_url = str(key.get("baseUrl") or base_url)
                model = str(key.get("model") or model)
            elif coding_settings_key:
                api_key = coding_settings_key
                base_url = coding_settings_base or base_url
                model = coding_settings_model or model
        else:
            active_coding = _active_coding_key(keys_mgr)
            if active_coding and active_coding.get("apiKey"):
                key_id = str(active_coding.get("id", key_id))
                api_key = str(active_coding.get("apiKey"))
                base_url = str(active_coding.get("baseUrl") or base_url)
                model = str(active_coding.get("model") or model)
            elif coding_settings_key:
                api_key = coding_settings_key
                base_url = coding_settings_base or base_url
                model = coding_settings_model or model

        if not api_key:
            active = keys_mgr.get_key() if keys_mgr else None
            if active and active.get("apiKey"):
                key_id = str(active.get("id", key_id))
                api_key = str(active.get("apiKey"))
                base_url = str(active.get("baseUrl") or base_url)
                model = str(active.get("model") or model)

    return ChatProfile(
        chat_mode=chat_mode,
        key_id=key_id,
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt_suffix=suffix,
    )
