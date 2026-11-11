"""Model access. Two modes, same interface:

live      - calls a model API for every stage. Every response is cached on disk by a hash of
            (provider, model, system, user), so a re-run costs nothing and results are reproducible.
            Provider is chosen with LLM_PROVIDER:
              anthropic (default)  needs ANTHROPIC_API_KEY
              gemini               needs GEMINI_API_KEY (free tier from aistudio.google.com)
recorded  - replays stage outputs stored in engine/recorded/judgments.json. No network, no key.

Model names can be overridden with TRIAGE_MODEL_STRONG / TRIAGE_MODEL_CHEAP.
To see which Gemini models your key can use:  python -m engine.llm --list-models
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()

_DEFAULTS = {
    #            strong (solving, judging)   cheap (reading comments, writing replies)
    "anthropic": ("claude-sonnet-5-5", "claude-haiku-5-5"),
    # Free tier: Pro models have no quota (HTTP 429) and gemini-2.5-pro is closed to new keys (404),
    # so the strong stages use the best Flash model the free tier serves.
    "gemini": ("gemini-3.8-flash", "gemini-3.5-flash-lite"),
}
if PROVIDER not in _DEFAULTS:
    raise RuntimeError(f"LLM_PROVIDER must be one of {sorted(_DEFAULTS)}, got {PROVIDER!r}")
STRONG = os.environ.get("TRIAGE_MODEL_STRONG", _DEFAULTS[PROVIDER][0])
CHEAP = os.environ.get("TRIAGE_MODEL_CHEAP", _DEFAULTS[PROVIDER][1])

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


def _extract_json(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model returned no JSON: " + text[:200])
    return json.loads(m.group(0))


def _need(var):
    val = os.environ.get(var)
    if not val:
        raise RuntimeError(f"{var} is not set. Use --mode recorded, or set {var} for --mode live (LLM_PROVIDER={PROVIDER}).")
    return val


def _post(url, body, headers, attempts=6):
    """POST JSON, retrying rate limits and server errors (free tiers rate-limit often)."""
    for i in range(attempts):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            # A daily quota will not recover by waiting seconds; stop now. Responses already cached
            # are kept, so re-running after the quota resets continues where this run stopped.
            daily = "per day" in detail or "PerDay" in detail
            if e.code not in (429, 500, 502, 503, 529) or daily or i == attempts - 1:
                raise RuntimeError(f"HTTP {e.code} from {url}: {detail[:600]}") from None
            wait = float(e.headers.get("retry-after") or min(60, 5 * 2 ** i))
            print(f"  rate limited / server busy (HTTP {e.code}), retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)


def _anthropic(system, user, model, max_tokens):
    # No temperature: current Sonnet/Haiku models reject non-default sampling values with a 400.
    # These models think before answering and thinking counts toward max_tokens, so the per-stage
    # value is only a floor; 16000 leaves room for thinking plus the JSON answer.
    payload = _post(
        "https://api.anthropic.com/v1/messages",
        {"model": model, "max_tokens": max(max_tokens, 16000),
         "system": system, "messages": [{"role": "user", "content": user}]},
        {"x-api-key": _need("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    if payload.get("stop_reason") in ("max_tokens", "refusal"):
        raise RuntimeError(f"model stopped with {payload['stop_reason']} (model={model})")
    return "".join(b.get("text", "") for b in payload["content"] if b.get("type") == "text")


def _gemini(system, user, model, max_tokens):
    # Gemini's OpenAI-compatible endpoint. Thinking models spend part of max_tokens on reasoning,
    # so the same 16000 floor applies. json_object mode keeps the reply parseable.
    payload = _post(
        GEMINI_BASE + "/chat/completions",
        {"model": model, "max_tokens": max(max_tokens, 16000),
         "response_format": {"type": "json_object"},
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        {"Authorization": "Bearer " + _need("GEMINI_API_KEY"), "content-type": "application/json"},
    )
    choice = payload["choices"][0]
    if choice.get("finish_reason") in ("length", "content_filter"):
        raise RuntimeError(f"model stopped with {choice['finish_reason']} (model={model})")
    return choice["message"].get("content") or ""


def call_json(system, user, model=STRONG, max_tokens=1500):
    key = hashlib.sha256(json.dumps([PROVIDER, model, system, user]).encode()).hexdigest()[:24]
    path = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    text = (_gemini if PROVIDER == "gemini" else _anthropic)(system, user, model, max_tokens)
    out = _extract_json(text)
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


if __name__ == "__main__":
    if "--list-models" in sys.argv:
        req = urllib.request.Request(GEMINI_BASE + "/models", headers={"Authorization": "Bearer " + _need("GEMINI_API_KEY")})
        with urllib.request.urlopen(req, timeout=60) as resp:
            for m in json.load(resp).get("data", []):
                print(m["id"].removeprefix("models/"))
    elif "--ping" in sys.argv:
        print(call_json('Reply with JSON only: {"ok": true, "model": "<your model name>"}', "ping", model=CHEAP))
    else:
        print(__doc__)
