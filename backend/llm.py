# LLM layer: two providers, same shape.
# Key always comes from the UI per request, never stored.

import os
import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


async def call_claude(api_key: str, model: str, system: str, user: str) -> str:
    """Direct Anthropic Messages API call."""
    if not model:
        model = "claude-3-5-sonnet-20241022"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 4000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(ANTHROPIC_URL, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    # Anthropic returns blocks: [{"type": "text", "text": "..."}]
    texts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(texts)


async def call_opencode(api_key: str, model: str, system: str, user: str, base_url: str = "") -> str:
    """OpenAI-compatible chat completions. Works for deepseek / openai / opencode gateways."""
    base_url = (base_url or os.getenv("OPENCODE_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    if not model:
        model = "deepseek-chat"
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


async def call_llm(provider: str, api_key: str, model: str, system: str, user: str, base_url: str = "") -> str:
    if provider == "claude":
        return await call_claude(api_key, model, system, user)
    return await call_opencode(api_key, model, system, user, base_url)
