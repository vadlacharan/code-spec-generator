# LLM layer: two providers, same shape.
# Key always comes from the UI per request, never stored.

import os
import httpx

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Go endpoint (bills your Go allowance). The non-Go /inference/openai/v1
# bills pay-as-you-go balance instead -> 402 when empty.
# Source: https://opencode.ai/inference/go/v1/models -> api base_url
OPENCODE_BASE_URL = "https://opencode.ai/inference/go/openai/v1"

# Go asks non-OpenCode clients to identify with their own UA + stable session id.
USER_AGENT = "ai-code-doc/1.0"


async def _post(client: httpx.AsyncClient, url: str, headers: dict, body: dict) -> dict:
    """POST and raise with the gateway's own error body (it usually explains 401/403/429)."""
    try:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500]
        raise RuntimeError(f"{e.response.status_code} from {url}: {detail}") from e
    return r.json()


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
        data = await _post(client, ANTHROPIC_URL, headers, body)
    # Anthropic returns blocks: [{"type": "text", "text": "..."}]
    texts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(texts)


async def call_opencode(api_key: str, model: str, system: str, user: str, base_url: str = "", session_id: str = "") -> str:
    """OpenAI-compatible chat completions. Works for deepseek / openai / opencode gateways."""
    base_url = (base_url or os.getenv("OPENCODE_BASE_URL", OPENCODE_BASE_URL)).rstrip("/")
    if not model:
        model = "deepseek-v4.1-flash"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if session_id:
        headers["x-opencode-session"] = session_id
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        data = await _post(client, f"{base_url}/chat/completions", headers, body)
    return data["choices"][0]["message"]["content"]


async def call_llm(provider: str, api_key: str, model: str, system: str, user: str, base_url: str = "", session_id: str = "") -> str:
    if provider == "claude":
        return await call_claude(api_key, model, system, user)
    return await call_opencode(api_key, model, system, user, base_url, session_id)
