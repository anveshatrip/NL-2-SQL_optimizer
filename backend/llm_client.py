import os
import re
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

PRICING: dict[str, dict[str, float]] = {
    # Gemini
    "gemini-2.0-flash":        {"input": 0.075,  "output": 0.30},
    "gemini-2.0-flash-lite":   {"input": 0.0375, "output": 0.15},
    "gemini-1.5-flash":        {"input": 0.075,  "output": 0.30},
    "gemini-1.5-pro":          {"input": 1.25,   "output": 5.00},
    # OpenAI
    "gpt-4o":                  {"input": 2.50,   "output": 10.00},
    "gpt-4o-mini":             {"input": 0.15,   "output": 0.60},
    "gpt-4-turbo":             {"input": 10.00,  "output": 30.00},
    # Anthropic
    "claude-3-5-haiku-20241022":  {"input": 0.80,  "output": 4.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00,  "output": 15.00},
    "claude-3-opus-20240229":     {"input": 15.00, "output": 75.00},
}


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated cost in USD for a single API call."""
    prices = PRICING.get(model, {"input": 0.0, "output": 0.0})
    return (
        input_tokens  * prices["input"]  / 1_000_000 +
        output_tokens * prices["output"] / 1_000_000
    )


def _clean_sql(raw: str) -> str:
    """Strip markdown code fences that LLMs sometimes add."""
    cleaned = re.sub(r"```(?:sql)?", "", raw, flags=re.IGNORECASE).strip()
    return cleaned.replace("`", "").strip()



@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float

def _call_gemini(prompt: str, model: str, temperature: float) -> LLMResult:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise EnvironmentError("GEMINI_API_KEY is not set in .env")
    genai.configure(api_key=api_key)

    gemini_model = genai.GenerativeModel(
        model_name=model,
        generation_config=GenerationConfig(
            temperature=temperature,
            max_output_tokens=1024,
            candidate_count=1,
        ),
    )

    t0 = time.perf_counter()
    response = gemini_model.generate_content(prompt)
    latency_ms = (time.perf_counter() - t0) * 1000

    # Gemini returns usage metadata
    usage = response.usage_metadata
    input_tokens  = getattr(usage, "prompt_token_count", 0)
    output_tokens = getattr(usage, "candidates_token_count", 0)

    return LLMResult(
        text=_clean_sql(response.text.strip()),
        provider="gemini",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_calculate_cost(model, input_tokens, output_tokens),
        latency_ms=round(latency_ms, 2),
    )


def _call_openai(prompt: str, model: str, temperature: float) -> LLMResult:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_openai_api_key_here":
        raise EnvironmentError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=api_key)

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=1024,
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    usage = response.usage
    input_tokens  = usage.prompt_tokens
    output_tokens = usage.completion_tokens
    raw_text = response.choices[0].message.content or ""

    return LLMResult(
        text=_clean_sql(raw_text.strip()),
        provider="openai",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_calculate_cost(model, input_tokens, output_tokens),
        latency_ms=round(latency_ms, 2),
    )


def _call_anthropic(prompt: str, model: str, temperature: float) -> LLMResult:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_anthropic_api_key_here":
        raise EnvironmentError("ANTHROPIC_API_KEY is not set in .env")

    client = anthropic.Anthropic(api_key=api_key)

    t0 = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    usage = response.usage
    input_tokens  = usage.input_tokens
    output_tokens = usage.output_tokens
    raw_text = response.content[0].text if response.content else ""

    return LLMResult(
        text=_clean_sql(raw_text.strip()),
        provider="anthropic",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_calculate_cost(model, input_tokens, output_tokens),
        latency_ms=round(latency_ms, 2),
    )

_PROVIDER_MAP = {
    "gemini":    _call_gemini,
    "openai":    _call_openai,
    "anthropic": _call_anthropic,
}

_DEFAULT_MODELS = {
    "gemini":    "gemini-2.0-flash",
    "openai":    "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
}


def call_llm(
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.05,
) -> LLMResult:

    provider = (provider or os.environ.get("DEFAULT_PROVIDER", "gemini")).lower()

    if provider not in _PROVIDER_MAP:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Choose from: {list(_PROVIDER_MAP.keys())}"
        )

    resolved_model = model or os.environ.get(
        f"{provider.upper()}_MODEL",
        _DEFAULT_MODELS[provider],
    )

    logger.info("LLM call → provider=%s model=%s", provider, resolved_model)

    result = _PROVIDER_MAP[provider](prompt, resolved_model, temperature)

    logger.info(
        "LLM done → %d tokens in / %d tokens out / $%.6f / %.0fms",
        result.input_tokens, result.output_tokens,
        result.cost_usd, result.latency_ms,
    )
    return result


def configure_gemini() -> None:
    """Kept for backward compatibility with main.py startup check."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    logger.info("Gemini SDK configured (model: %s)", _DEFAULT_MODELS["gemini"])


def translate_nl_to_sql(prompt: str, provider: str = "gemini", model: str = None) -> str:
    """Legacy wrapper — returns just the SQL string."""
    return call_llm(prompt, provider=provider, model=model, temperature=0.05).text


def rewrite_sql_for_optimization(prompt: str, provider: str = "gemini", model: str = None) -> str:
    """Legacy wrapper — returns just the rewritten SQL string."""
    return call_llm(prompt, provider=provider, model=model, temperature=0.20).text
